import smtplib
from collections.abc import Mapping
from email.message import EmailMessage
from typing import Any


def smtp_is_configured(settings: Mapping[str, Any]) -> bool:
    return all(
        isinstance(settings.get(key), str) and settings[key].strip()
        for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM")
    )


def send_email_message(message: EmailMessage, settings: Mapping[str, Any]) -> None:
    if not smtp_is_configured(settings):
        raise RuntimeError("SMTP email delivery is not configured.")

    with smtplib.SMTP(settings["SMTP_HOST"], settings["SMTP_PORT"], timeout=10) as server:
        server.starttls()
        server.login(settings["SMTP_USER"], settings["SMTP_PASSWORD"])
        server.send_message(message)
