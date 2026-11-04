"""Sending emails (password reset, email verification).

EMAIL_BACKEND=console (default) prints the message, including its link, to the backend's terminal,
so password reset works without a mail server. EMAIL_BACKEND=smtp sends it with the SMTP_* settings.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger("bookmind.email")
sent: list[dict] = []  # the last messages (console backend), for tests


async def send_email(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if s.email_backend.lower() == "smtp" and s.smtp_host:
        await asyncio.to_thread(_send_smtp, to, subject, body)
        return
    sent.append({"to": to, "subject": subject, "body": body})
    del sent[:-20]
    line = "=" * 70
    log.warning("\n%s\n EMAIL (dev mode: printed instead of sent)\n To: %s\n Subject: %s\n\n%s\n%s",
                line, to, subject, body, line)


def _send_smtp(to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        if s.smtp_tls:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
