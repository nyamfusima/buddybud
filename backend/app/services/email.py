import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("buddybud.email")


def send_email(to: str, subject: str, body: str) -> None:
    """Send via SMTP when configured; otherwise log it (dev). Never raises into the request."""
    s = get_settings()
    if not s.smtp_host:
        if s.env == "prod":  # never write passwords or reset links to production logs
            log.error("SMTP not configured: email to %s (%s) was NOT sent", to, subject)
        else:
            log.warning("EMAIL (SMTP not configured, dev only) to=%s subject=%s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    except Exception:  # pragma: no cover - network
        log.exception("Failed to send email to %s", to)
