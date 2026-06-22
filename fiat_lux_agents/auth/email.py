"""Email sender abstraction for fla-auth.

Configured via env vars at send time:
  SENDGRID_API_KEY  - if set, sends via Sendgrid HTTP API
  SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS - fallback SMTP

Neither set? send() raises RuntimeError so the caller can surface a
useful error rather than silently swallowing it.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send(to: str, subject: str, body_html: str, from_email: str) -> None:
    """Send an email. Raises RuntimeError if no provider is configured."""
    api_key = os.environ.get("SENDGRID_API_KEY", "")
    if api_key:
        _send_sendgrid(api_key, from_email, to, subject, body_html)
        return

    smtp_host = os.environ.get("SMTP_HOST", "")
    if smtp_host:
        _send_smtp(smtp_host, from_email, to, subject, body_html)
        return

    raise RuntimeError(
        "No email provider configured. Set SENDGRID_API_KEY or SMTP_HOST."
    )


def _send_sendgrid(
    api_key: str, from_email: str, to: str, subject: str, body_html: str
) -> None:
    import urllib.request
    import json

    payload = json.dumps({
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/html", "value": body_html}],
    }).encode()

    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        if resp.status not in (200, 202):
            raise RuntimeError(f"Sendgrid returned {resp.status}")


def _send_smtp(
    smtp_host: str, from_email: str, to: str, subject: str, body_html: str
) -> None:
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        if smtp_user:
            server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, to, msg.as_string())
