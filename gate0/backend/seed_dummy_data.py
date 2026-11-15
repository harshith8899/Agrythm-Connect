"""Seed script to populate gate0/backend/weathercall.db with rich, realistic dummy data.
Includes diverse farmer profiles, 14 days of call logs, callbacks, and alerts.
"""
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "weathercall.db"

FARMERS = [
    {
        "farmer_id": "F001",
        "name": "Ramesh Patil",
        "phone": "9845123456",
        "language": "kn",
        "village": "Betageri",
        "district": "Gadag",
        "state": "Karnataka",
        "lat": 15.4332,
        "lon": 75.6421,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F002",
        "name": "Suresh Gowda",
        "phone": "9448123789",
        "language": "kn",
        "village": "Navalgund",
        "district": "Dharwad",
        "state": "Karnataka",
        "lat": 15.5621,
        "lon": 75.3611,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F003",
        "name": "Neha Sharma",
        "phone": "6361385556",
        "language": "hi",
        "village": "Gadag Rural",
        "district": "Gadag",
        "state": "Karnataka",
        "lat": 15.4297,
        "lon": 75.6297,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F004",
        "name": "Basavarajappa Hiremath",
        "phone": "9900456123",
        "language": "kn",
        "village": "Ranebennur",
        "district": "Haveri",
        "state": "Karnataka",
        "lat": 14.6214,
        "lon": 75.6247,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F005",
        "name": "Lakshmi Devi",
        "phone": "8762345987",
        "language": "kn",
        "village": "Gokak",
        "district": "Belagavi",
        "state": "Karnataka",
        "lat": 16.1667,
        "lon": 74.8333,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F006",
        "name": "Anand Kumar Reddy",
        "phone": "9449876543",
        "language": "te",
        "village": "Sandur",
        "district": "Ballari",
        "state": "Karnataka",
        "lat": 15.0833,
        "lon": 76.5500,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F007",
        "name": "Manjula Bai",
        "phone": "9880123987",
        "language": "kn",
        "village": "Jamkhandi",
        "district": "Bagalkote",
        "state": "Karnataka",
        "lat": 16.5000,
        "lon": 75.3000,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F008",
        "name": "Rajesh Singh",
        "phone": "9741567890",
        "language": "hi",
        "village": "Kushtagi",
        "district": "Koppal",
        "state": "Karnataka",
        "lat": 15.7500,
        "lon": 76.2000,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F009",
        "name": "Shivakumar Swamy",
        "phone": "9611234567",
        "language": "kn",
        "village": "Nargund",
        "district": "Gadag",
        "state": "Karnataka",
        "lat": 15.7167,
        "lon": 75.3833,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F010",
        "name": "David Fernandez",
        "phone": "9480345678",
        "language": "en",
        "village": "Channagiri",
        "district": "Davanagere",
        "state": "Karnataka",
        "lat": 14.0267,
        "lon": 75.9267,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F011",
        "name": "Venkat Rao Naidu",
        "phone": "9945678123",
        "language": "te",
        "village": "Hospet",
        "district": "Ballari",
        "state": "Karnataka",
        "lat": 15.2667,
        "lon": 76.4000,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F012",
        "name": "Parameshwarappa",
        "phone": "9844567890",
        "language": "kn",
        "village": "Byadgi",
        "district": "Haveri",
        "state": "Karnataka",
        "lat": 14.6833,
        "lon": 75.4833,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F013",
        "name": "Savitri Kulkarni",
        "phone": "9731234567",
        "language": "kn",
        "village": "Kalghatgi",
        "district": "Dharwad",
        "state": "Karnataka",
        "lat": 15.1833,
        "lon": 74.9667,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F014",
        "name": "Amitabh Verma",
        "phone": "9620345678",
        "language": "hi",
        "village": "Shirhatti",
        "district": "Gadag",
        "state": "Karnataka",
        "lat": 15.2333,
        "lon": 75.5833,
        "consent": 1,
        "active": 1,
    },
    {
        "farmer_id": "F015",
        "name": "Shantamma",
        "phone": "9449123890",
        "language": "kn",
        "village": "Bailhongal",
        "district": "Belagavi",
        "state": "Karnataka",
        "lat": 15.8167,
        "lon": 74.8667,
        "consent": 1,
        "active": 0,  # Inactive farmer for testing toggle
    },
    {
        "farmer_id": "F016",
        "name": "Somasekhar",
        "phone": "9901234567",
        "language": "kn",
        "village": "Mundargi",
        "district": "Gadag",
        "state": "Karnataka",
        "lat": 15.2083,
        "lon": 75.8833,
        "consent": 1,
        "active": 1,
    },
]

KANNADA_TRANSCRIPT_COMPLETED = [
    {"speaker": "agent", "text": "ನಮಸ್ಕಾರ ರಮೇಶ್ ಅವರೇ, ಇದು ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್‌ನಿಂದ ಗದಗ ಪ್ರದೇಶದ ಇಂದಿನ ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ."},
    {"speaker": "farmer", "text": "ನಮಸ್ಕಾರ, ಇವತ್ತು ಮಳೆ ಬರೋ ಸಾಧ್ಯತೆ ಇದೆಯಾ?"},
    {"speaker": "agent", "text": "ಇಂದು ಗರಿಷ್ಠ ತಾಪಮಾನ 31 ಡಿಗ್ರಿ, ಸಂಜೆ 4 ಗಂಟೆಯ ನಂತರ ಲಘು ಮಳೆಯಾಗುವ 65% ಸಾಧ್ಯತೆಯಿದೆ. ಗಾಳಿಯ ವೇಗ ಗಂಟೆಗೆ 14 ಕಿ.ಮೀ ಇರುತ್ತದೆ."},
    {"speaker": "farmer", "text": "ಸರಿ, ಹಾಗಾದ್ರೆ ಕೀಟನಾಶಕ ಸಿಂಪಡಣೆಯನ್ನು ನಾಳೆಗೆ ಮುಂದೂಡುತ್ತೇನೆ. ಧನ್ಯವಾದ."},
    {"speaker": "agent", "text": "ತುಂಬಾ ಧನ್ಯವಾದಗಳು, ಶುಭ ದಿನ."},
]

HINDI_TRANSCRIPT_COMPLETED = [
    {"speaker": "agent", "text": "नमस्ते नेहा जी, यह एग्रीदम कनेक्ट से आज का मौसम समाचार है।"},
    {"speaker": "farmer", "text": "हाँ बताइए, आज धूप कैसी रहेगी?"},
    {"speaker": "agent", "text": "आज अधिकतम तापमान 32 डिग्री सेल्सियस और न्यूनतम 21 डिग्री रहेगा। दिनभर मौसम साफ रहेगा, बारिश की कोई संभावना नहीं है।"},
    {"speaker": "farmer", "text": "बहुत अच्छा, आज हम खेत में कटाई शुरू कर सकते हैं। धन्यवाद।"},
    {"speaker": "agent", "text": "शुभ दिन नेहा जी, एग्रीदम कनेक्ट से जुड़ने के लिए धन्यवाद।"},
]

TELUGU_TRANSCRIPT_COMPLETED = [
    {"speaker": "agent", "text": "నమస్కారం ఆనంద్ గారు, అగ్రిథమ్ కనెక్ట్ నుండి నేటి వాతావరణ సమాచారం."},
    {"speaker": "farmer", "text": "నమస్తే, ఈ రోజు వర్షం పడే అవకాశం ఉందా?"},
    {"speaker": "agent", "text": "ఈ రోజు గరిష్ట ఉష్ణోగ్రత 33 డిగ్రీలు ఉంటుంది. సాయంత్రం వేళల్లో ఉరుములతో కూడిన జల్లులు పడే అవకాశం 40% ఉంది."},
    {"speaker": "farmer", "text": "అలాగే, నీటి పారుదల ఏర్పాట్లు చేసుకుంటాను. ధన్యవాదాలు."},
    {"speaker": "agent", "text": "ధన్యవాదాలు ఆనంద్ గారు."},
]

ENGLISH_TRANSCRIPT_COMPLETED = [
    {"speaker": "agent", "text": "Hello David, this is Agrythm Connect with your daily agricultural weather briefing."},
    {"speaker": "farmer", "text": "Hello! What is the humidity and rain outlook today?"},
    {"speaker": "agent", "text": "Today's high is 30°C, humidity will hover around 68%, with a 20% slight chance of morning drizzle. Wind gusts up to 12 km/h."},
    {"speaker": "farmer", "text": "Understood, perfect for our planned field fertilization today. Thank you."},
    {"speaker": "agent", "text": "Have a productive day ahead!"},
]

CALLBACK_TRANSCRIPT = [
    {"speaker": "agent", "text": "ನಮಸ್ಕಾರ ಬಸವರಾಜಪ್ಪ ಅವರೇ, ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್‌ನಿಂದ ಹವಾಮಾನ ಮಾಹಿತಿ ತಿಳಿಸಲು ಕರೆ ಮಾಡಿದ್ದೇವೆ."},
    {"speaker": "farmer", "text": "ನಾನು ಈಗ ಮಾರುಕಟ್ಟೆಯಲ್ಲಿದ್ದೇನೆ, ತುಂಬಾ ಗದ್ದಲವಿದೆ. ಇನ್ನೆರಡು ಗಂಟೆ ಬಿಟ್ಟು ಮಧ್ಯಾಹ್ನ ಕರೆ ಮಾಡಿ."},
    {"speaker": "agent", "text": "ಖಂಡಿತ, ಮಧ್ಯಾಹ್ನ 2 ಗಂಟೆಗೆ ನಿಮ್ಮನ್ನು ಮತ್ತೆ ಸಂಪರ್ಕಿಸುತ್ತೇವೆ. ಧನ್ಯವಾದ."},
]


def seed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print(f"Connecting to {DB_PATH}...")

    # 1. Clear existing data
    cur.execute("DELETE FROM dash_farmers")
    cur.execute("DELETE FROM dash_results")
    cur.execute("DELETE FROM dash_callbacks")
    cur.execute("DELETE FROM dash_alerts")
    cur.execute("DELETE FROM dash_retries")
    cur.execute("DELETE FROM dash_tests")
    cur.execute("DELETE FROM dash_live")

    # 2. Insert Farmers
    for f in FARMERS:
        cur.execute(
            """
            INSERT INTO dash_farmers(farmer_id, name, phone, language, village, district, state, lat, lon, consent, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f["farmer_id"],
                f["name"],
                f["phone"],
                f["language"],
                f["village"],
                f["district"],
                f["state"],
                f["lat"],
                f["lon"],
                f["consent"],
                f["active"],
            ),
        )
    print(f"Inserted {len(FARMERS)} farmers into dash_farmers.")

    # 3. Generate 14 days of call logs ending today (2026-11-15)
    today = date(2026, 11, 15)

    call_records = []

    # Daily templates for distribution across the 14 days
    for day_offset in range(13, -1, -1):
        target_date = today - timedelta(days=day_offset)
        date_str = target_date.isoformat()

        # How many calls on this day
        if day_offset == 0:
            # Today: 10 calls with diverse live states
            day_farmer_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        elif day_offset == 1:
            # Yesterday: 12 calls
            day_farmer_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12]
        else:
            # Past days: 6-10 calls
            count = 6 + (day_offset % 5)
            day_farmer_indices = [(i + day_offset) % len(FARMERS) for i in range(count)]

        for idx in day_farmer_indices:
            farmer = FARMERS[idx]
            fid = farmer["farmer_id"]
            lang = farmer["language"]

            # Weather JSON
            temp_min = round(19.0 + (idx * 0.3) % 4, 1)
            temp_max = round(30.0 + (idx * 0.5) % 5, 1)
            wind = round(10.0 + (idx * 0.7) % 8, 1)
            rain = int((idx * 13 + day_offset * 7) % 85)
            humidity = int(50 + (idx * 4) % 35)

            weather_obj = {
                "temp_min": temp_min,
                "temp_max": temp_max,
                "wind": wind,
                "rain": rain,
                "humidity": humidity,
                "source": "Open-Meteo",
            }
            weather_json = json.dumps(weather_obj)

            # Assign realistic outcomes
            attempt_id = f"SARVAM-{target_date.strftime('%Y%m%d')}-{fid}-{uuid.uuid4().hex[:6]}"

            # Randomize outcomes plausibly:
            # 65% Completed, 15% Callback, 12% Unanswered/Busy, 8% Failed
            outcome_seed = (idx * 7 + day_offset * 11) % 100

            if outcome_seed < 62:
                # Completed
                status = "answered"
                note = ""
                duration = 65 + (idx * 17) % 110
                understood = "yes"
                stop = "no"
                cb_time = ""
                summary = f"Farmer confirmed receipt of {farmer['village']} weather forecast ({rain}% rain chance). Advised on optimal spraying window."
                if lang == "hi":
                    transcript = json.dumps(HINDI_TRANSCRIPT_COMPLETED)
                elif lang == "te":
                    transcript = json.dumps(TELUGU_TRANSCRIPT_COMPLETED)
                elif lang == "en":
                    transcript = json.dumps(ENGLISH_TRANSCRIPT_COMPLETED)
                else:
                    transcript = json.dumps(KANNADA_TRANSCRIPT_COMPLETED)

            elif outcome_seed < 78:
                # Callback Scheduled
                status = "answered"
                note = "Callback requested"
                duration = 45 + (idx * 5) % 30
                understood = ""
                stop = "no"
                cb_time = "in 2 hours" if day_offset == 0 else "at 3 PM"
                summary = f"Farmer was busy in the market. Requested a callback later in the day."
                transcript = json.dumps(CALLBACK_TRANSCRIPT)

            elif outcome_seed < 88:
                # Unanswered
                status = "no_answer"
                note = "No answer from farmer's handset after 6 rings"
                duration = 0
                understood = ""
                stop = ""
                cb_time = ""
                summary = "Call rang out without answer."
                transcript = ""

            elif outcome_seed < 94:
                # Busy
                status = "busy"
                note = "User busy signal received"
                duration = 0
                understood = ""
                stop = ""
                cb_time = ""
                summary = "Line busy on carrier network."
                transcript = ""

            else:
                # Failed / Network drop
                status = "failed"
                note = "Carrier telecom pulse timeout / network congestion"
                duration = 14
                understood = "no"
                stop = "no"
                cb_time = ""
                summary = "Call dropped during carrier audio channel handshake."
                transcript = ""

            # Updated at timestamp (between 07:30 and 11:45 AM of that day)
            call_hour = 7 + (idx % 4)
            call_minute = (idx * 6 + day_offset * 4) % 60
            updated_at = f"{date_str}T{call_hour:02d}:{call_minute:02d}:00"

            call_records.append(
                (
                    fid,
                    date_str,
                    status,
                    note,
                    weather_json,
                    attempt_id,
                    "sarvam_agent",
                    lang,
                    duration,
                    summary,
                    cb_time,
                    understood,
                    stop,
                    transcript,
                    updated_at,
                )
            )

    # Insert into dash_results
    cur.executemany(
        """
        INSERT OR REPLACE INTO dash_results(
            farmer_id, call_date, status, note, weather, attempt_id, mode, language,
            duration_s, call_summary, callback_time, understood_weather, stop_calls_requested,
            transcript, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        call_records,
    )
    print(f"Inserted {len(call_records)} call records into dash_results.")

    # 4. Insert Active Callbacks for Today
    callbacks = [
        (
            "F004",
            "2026-11-15T14:30:00",
            "2026-11-15",
            "pending",
            "Scheduled afternoon callback",
            "SARVAM-CB-F004",
            "Farmer was in market during morning dispatch. Requested call at 2:30 PM.",
            "",
            "in 2 hours",
            "2026-11-15T09:15:00",
            0,
        ),
        (
            "F006",
            "2026-11-15T16:00:00",
            "2026-11-15",
            "pending",
            "Evening callback requested",
            "SARVAM-CB-F006",
            "Requested evening call after field inspection.",
            "",
            "at 4 PM",
            "2026-11-15T09:40:00",
            0,
        ),
    ]
    cur.executemany(
        """
        INSERT OR REPLACE INTO dash_callbacks(
            farmer_id, due_at, source_date, status, note, attempt_id,
            call_summary, understood_weather, requested_text, updated_at, reschedules
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        callbacks,
    )
    print(f"Inserted {len(callbacks)} callbacks into dash_callbacks.")

    # 5. Insert Alerts
    alerts = [
        (
            "2026-11-15T08:45:00",
            "high_wind",
            "F005",
            "High wind advisory (18 km/h) active for Gokak cluster, Belagavi. Farmers notified.",
        ),
        (
            "2026-11-15T09:30:00",
            "callback_scheduled",
            "F004",
            "Basavarajappa Hiremath requested afternoon callback at 2:30 PM.",
        ),
        (
            "2026-11-14T10:15:00",
            "rain_forecast",
            "F001",
            "65% heavy precipitation advisory delivered for Betageri village.",
        ),
    ]
    cur.executemany(
        """
        INSERT INTO dash_alerts(at, kind, farmer_id, text)
        VALUES (?, ?, ?, ?)
        """,
        alerts,
    )
    print(f"Inserted {len(alerts)} alerts into dash_alerts.")

    # 6. Insert live queue for real-time demo
    cur.execute(
        """
        INSERT OR REPLACE INTO dash_live(farmer_id, call_date, kind, attempt_no, state, since)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("F016", "2026-11-15", "daily", 1, "calling", "2026-11-15T12:30:00"),
    )
    print("Added 1 active live call into dash_live.")

    conn.commit()
    conn.close()
    print("Dummy data seeding complete!")


if __name__ == "__main__":
    seed()
