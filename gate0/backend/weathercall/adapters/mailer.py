"""Email sender (the message channel while WhatsApp and SMS are not available).

Chosen by the environment, never by code: with GATE0_SMTP_HOST set mail goes out over SMTP, otherwise nothing is sent
and the message is recorded as 'not configured'. The password is read from GATE0_SMTP_PASSWORD (Render environment, secret)
and is never logged, stored or put in an error text; errors name only their type.

  GATE0_SMTP_HOST      e.g. smtp.gmail.com
  GATE0_SMTP_PORT      587 (STARTTLS, the default) or 465 (SSL)
  GATE0_SMTP_USER      the sending account
  GATE0_SMTP_PASSWORD  its password or app password
  GATE0_MAIL_FROM      the From address (default: the user)
  GATE0_MAIL_TEAM      optional team address that receives a copy of every message (Bcc) for monitoring

Or, where SMTP is blocked (Render's free plan), an HTTPS mail API: GATE0_RESEND_API_KEY (Resend), with GATE0_MAIL_FROM and
GATE0_MAIL_LOGO_URL; when the key is set it is used instead of SMTP.
"""
from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path

LOGO_FILE = Path(__file__).resolve().parent.parent / "assets" / "agrythm-logo.png"
LOGO_CID = "agrythm-logo"             # the HTML refers to it as <img src="cid:agrythm-logo">


class MailNotConfigured(Exception):
    pass


class MailHTTPError(RuntimeError):
    """A mail API answered with an error. safe_text names the HTTP code and the API's error name, never its message
    (a message could quote the address)."""

    def __init__(self, safe_text: str):
        super().__init__(safe_text)
        self.safe_text = safe_text


class NullMailer:
    """No mail settings: nothing is sent."""
    label = "not configured"
    live = False

    def send(self, to: str, subject: str, body: str, html: str = "") -> None:
        raise MailNotConfigured()


class RecordingMailer:
    """For tests: keeps what would have been sent."""
    label = "recording"
    live = False

    def __init__(self, fail: bool = False):
        self.sent: list[tuple[str, str, str]] = []
        self.html: list[str] = []
        self.fail = fail

    def send(self, to: str, subject: str, body: str, html: str = "") -> None:
        if self.fail:
            raise ConnectionError("simulated")
        self.sent.append((to, subject, body))
        self.html.append(html)


class SmtpMailer:
    label = "SMTP"
    live = True

    def __init__(self, host: str, port: int, user: str, password: str, sender: str = "", team: str = "", timeout: float = 15.0):
        self.host, self.port, self.user, self._password = host, port, user, password
        self.sender, self.team, self.timeout = sender or user, team, timeout

    def build(self, to: str, subject: str, body: str, html: str = "") -> EmailMessage:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        if self.team:
            msg["Bcc"] = self.team
        msg.set_content(body)                      # plain text, for mail apps that do not show HTML
        if html:
            msg.add_alternative(html, subtype="html")
            if LOGO_FILE.is_file():                # the logo travels inside the mail, so it shows without 'load images'
                msg.get_payload()[1].add_related(LOGO_FILE.read_bytes(), "image", "png", cid=f"<{LOGO_CID}>",
                                                 filename="agrythm-logo.png", disposition="inline")
        return msg

    def send(self, to: str, subject: str, body: str, html: str = "") -> None:
        msg = self.build(to, subject, body, html)
        ctx = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ctx) as s:
                s.login(self.user, self._password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                s.starttls(context=ctx)
                s.login(self.user, self._password)
                s.send_message(msg)

    def __repr__(self) -> str:                      # never shows the password
        return f"SmtpMailer({self.host}:{self.port})"


class ResendMailer:
    """Sends through Resend's HTTPS API (port 443). Render's free plan blocks the SMTP ports, so SMTP cannot be used there.
    GATE0_RESEND_API_KEY is the key (secret, Render environment); GATE0_MAIL_FROM the sender (default
    'Agrythm <onboarding@resend.dev>', which Resend only lets deliver to the account owner's own address: fine while
    testing with GATE0_MAIL_TEST_TO); GATE0_MAIL_LOGO_URL a public https address of the logo (without one the logo is left out)."""
    label = "Resend"
    live = True
    URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str = "", team: str = "", logo_url: str = "", timeout: float = 15.0,
                 opener=urllib.request.urlopen):
        self._key = api_key
        self.sender = sender or "Agrythm <onboarding@resend.dev>"
        self.team, self.logo_url, self.timeout, self._open = team, logo_url, timeout, opener

    def payload(self, to: str, subject: str, body: str, html: str = "") -> dict:
        data = {"from": self.sender, "to": [to], "subject": subject, "text": body}
        if self.team:
            data["bcc"] = [self.team]
        if html:                                           # the logo is a web address here, not an attachment
            if self.logo_url:
                html = html.replace("cid:" + LOGO_CID, self.logo_url)
            else:
                html = re.sub(r'<img src="cid:' + LOGO_CID + r'"[^>]*>', "", html)
            data["html"] = html
        return data

    def send(self, to: str, subject: str, body: str, html: str = "") -> None:
        req = urllib.request.Request(
            self.URL, data=json.dumps(self.payload(to, subject, body, html)).encode(), method="POST",
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
                     "User-Agent": "agrythm-gate0/1.0"})
        try:
            with self._open(req, timeout=self.timeout):
                return
        except urllib.error.HTTPError as exc:
            try:
                name = str(json.load(exc).get("name") or "")
            except Exception:
                name = ""
            raise MailHTTPError(f"HTTP {exc.code} {name}".strip()[:80]) from None

    def __repr__(self) -> str:                      # never shows the key
        return "ResendMailer()"


def make_mailer(env: dict | None = None):
    e = env if env is not None else os.environ
    key = (e.get("GATE0_RESEND_API_KEY") or "").strip()
    if key:
        return ResendMailer(key, (e.get("GATE0_MAIL_FROM") or "").strip(), (e.get("GATE0_MAIL_TEAM") or "").strip(),
                            (e.get("GATE0_MAIL_LOGO_URL") or "").strip())
    host = (e.get("GATE0_SMTP_HOST") or "").strip()
    if not host:
        return NullMailer()
    return SmtpMailer(host, int(e.get("GATE0_SMTP_PORT") or 587), (e.get("GATE0_SMTP_USER") or "").strip(),
                      e.get("GATE0_SMTP_PASSWORD") or "", (e.get("GATE0_MAIL_FROM") or "").strip(),
                      (e.get("GATE0_MAIL_TEAM") or "").strip())
