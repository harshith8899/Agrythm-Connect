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
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

LOGO_FILE = Path(__file__).resolve().parent.parent / "assets" / "agrythm-logo.png"
LOGO_CID = "agrythm-logo"             # the HTML refers to it as <img src="cid:agrythm-logo">


class MailNotConfigured(Exception):
    pass


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


def make_mailer(env: dict | None = None):
    e = env if env is not None else os.environ
    host = (e.get("GATE0_SMTP_HOST") or "").strip()
    if not host:
        return NullMailer()
    return SmtpMailer(host, int(e.get("GATE0_SMTP_PORT") or 587), (e.get("GATE0_SMTP_USER") or "").strip(),
                      e.get("GATE0_SMTP_PASSWORD") or "", (e.get("GATE0_MAIL_FROM") or "").strip(),
                      (e.get("GATE0_MAIL_TEAM") or "").strip())
