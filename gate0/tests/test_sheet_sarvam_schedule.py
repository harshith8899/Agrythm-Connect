import base64
import io
import json
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from weathercall import ports as P
from weathercall.adapters.local import InMemoryFarmerSource, SQLiteLedger, demo_farmers
from weathercall.adapters.mock import MockTelephony, MockWeather
from weathercall.adapters.sarvam import SarvamVoice
from weathercall.adapters.sheet import SheetFarmerSource, load_farmers
from weathercall.cli import in_window, load_env_file, main
from weathercall.config import Settings
from weathercall.contracts import CallRequest, FinalResult, Language
from weathercall.engine import Ports, process_request
from weathercall.schedule import task_xml

D = date(2026, 11, 5)
HEADER = "Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent\n"


def write(tmp_path, body, header=HEADER, name="farmers.csv"):
    f = tmp_path / name
    f.write_text(header + body, encoding="utf-8")
    return f


def test_example_sheet_loads_and_fits_the_port():
    src = SheetFarmerSource(Path(__file__).parent.parent / "farmers.example.csv")
    assert isinstance(src, P.FarmerSource) and len(src.list_callable_ids(D)) >= 3


def test_csv_columns_mapped_and_values_normalised(tmp_path):
    f = write(tmp_path, "F1,Ramesh,98765 43210,Mandya,Mandya,Karnataka,Hindi,Yes\n"
                        "F2,Lakshmi,9000000000,,Mysuru,Karnataka,english,no\n"
                        ",,,,,,,\n")
    a, b = load_farmers(f)
    assert (a.farmer_id, a.display_name, a.language, a.place_name, a.consent, a.phone) == \
           ("F1", "Ramesh", Language.HI, "Mandya", True, "9876543210")
    assert (b.language, b.place_name, b.consent, b.active) == (Language.EN, "Mysuru", False, True)


def test_excel_sheet_reads_numeric_phone(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.active.append(["Farmer ID", "Farmer Name", "Mobile Number", "Village", "Preferred Calling Language",
                      "Call Consent", "Active"])
    wb.active.append(["F9", "Kavya", 9123456789, "Hassan", "EN", "TRUE", "No"])
    f = tmp_path / "farmers.xlsx"
    wb.save(f)
    (k,) = load_farmers(f)
    assert k.phone == "9123456789" and k.active is False and k.consent is True


@pytest.mark.parametrize("body, needle", [
    ("F1,A,1,X,X,X,Tamil,yes\n", "language"),
    ("F1,A,1,X,X,X,Hindi,yes\nF1,B,2,X,X,X,Hindi,yes\n", "twice"),
    (",A,1,X,X,X,Hindi,yes\n", "empty"),
])
def test_bad_rows_are_reported_without_phone(tmp_path, body, needle):
    with pytest.raises(ValueError, match=needle) as e:
        load_farmers(write(tmp_path, body))
    assert "9876" not in str(e.value)


def test_missing_required_column_is_named(tmp_path):
    with pytest.raises(ValueError, match="consent"):
        load_farmers(write(tmp_path, "F1,A,1,X\n", header="Farmer ID,Farmer Name,Mobile Number,Village\n"))


class FakeHTTP:
    def __init__(self):
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        return io.BytesIO(json.dumps({"audios": [base64.b64encode(b"RIFFfake").decode()]}).encode())


def test_sarvam_request_shape_and_cached_audio(tmp_path):
    http = FakeHTTP()
    v = SarvamVoice(api_key="sk-test", out_dir=tmp_path, opener=http)
    assert isinstance(v, P.VoiceProvider) and "sk-test" not in repr(v)
    ref = v.synthesize("नमस्ते", Language.HI)
    assert Path(ref).read_bytes() == b"RIFFfake"
    req = http.requests[0]
    body = json.loads(req.data)
    assert req.full_url == "https://api.sarvam.ai/text-to-speech"
    assert req.get_header("Api-subscription-key") == "sk-test"
    assert body["language_code"] == "hi-IN" and body["text"] == "नमस्ते"
    assert v.synthesize("नमस्ते", Language.HI) == ref and len(http.requests) == 1


def test_sarvam_without_key_is_loud(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SARVAM_API_KEY"):
        SarvamVoice()


def test_voice_outage_fails_one_farmer_and_dials_nobody():
    class DownVoice:
        def synthesize(self, text, language):
            raise ConnectionError("sarvam down")
    ports = Ports(InMemoryFarmerSource(demo_farmers()), SQLiteLedger(), MockWeather(), DownVoice(), MockTelephony())
    r = process_request(CallRequest("F001", D), ports, Settings())
    assert r.result is FinalResult.FAILED and ports.telephony._count == {}


def test_env_file_drops_inline_comments_and_never_overrides(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# header\nGATE0_T1=sarvam   # real voice\nGATE0_T2=\"x\"\nGATE0_T3=file\n", encoding="utf-8")
    monkeypatch.setenv("GATE0_T3", "env")
    for k in ("GATE0_T1", "GATE0_T2"):
        monkeypatch.delenv(k, raising=False)
    load_env_file(f)
    import os
    assert (os.environ["GATE0_T1"], os.environ["GATE0_T2"], os.environ["GATE0_T3"]) == ("sarvam", "x", "env")
    for k in ("GATE0_T1", "GATE0_T2"):
        monkeypatch.delenv(k)


def test_campaign_window():
    start = date(2026, 10, 27)
    assert [in_window(date(2026, 10, d), start, 4) for d in (26, 27, 30, 31)] == [False, True, True, False]
    assert in_window(D, None, None)


def test_cli_outside_window_runs_nothing(tmp_path, capsys):
    assert main(["--date", "2026-11-05", "--window-start", "2026-10-27", "--window-days", "4",
                 "--log-dir", str(tmp_path)], env_file=None) == 0
    assert "nothing to do" in (tmp_path / "run-2026-11-05.log").read_text(encoding="utf-8")


def test_task_runs_daily_at_call_time_and_expires(tmp_path):
    xml = task_xml(date(2026, 10, 27), 4, "09:00", r"C:\Python\python.exe", tmp_path)
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    root = ET.fromstring(xml.split("?>", 1)[1])
    trig = root.find("t:Triggers/t:CalendarTrigger", ns)
    assert trig.find("t:StartBoundary", ns).text == "2026-10-27T09:00:00"
    assert trig.find("t:EndBoundary", ns).text == "2026-10-30T23:59:59"
    assert trig.find("t:ScheduleByDay/t:DaysInterval", ns).text == "1"
    assert "--window-start 2026-10-27 --window-days 4" in root.find("t:Actions/t:Exec/t:Arguments", ns).text
