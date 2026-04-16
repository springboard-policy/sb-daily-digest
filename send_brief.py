"""
Email utilities for the Springboard Daily Digest.

Required GitHub secrets / environment variables:
  EMAIL_FROM      – sender address (e.g. digest@springboardpolicy.com)
  EMAIL_PASSWORD  – app password for that address (Gmail / Google Workspace:
                    myaccount.google.com/apppasswords)
  EMAIL_TO        – comma-separated recipient list

Optional:
  SMTP_HOST  (default: smtp.gmail.com)
  SMTP_PORT  (default: 587)
"""

import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _smtp_send(subject: str, html_body: str) -> None:
    smtp_host  = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port  = int(os.environ.get("SMTP_PORT", "587"))
    sender     = os.environ.get("EMAIL_FROM", "")
    password   = os.environ.get("EMAIL_PASSWORD", "")
    recipients = [r.strip() for r in os.environ.get("EMAIL_TO", "").split(",") if r.strip()]

    if not sender or not password or not recipients:
        print("  Email skipped: EMAIL_FROM, EMAIL_PASSWORD, or EMAIL_TO not set.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        print(f"  Emailed to: {', '.join(recipients)}")
    except Exception as e:
        print(f"  Email failed: {e}", file=sys.stderr)


def send_brief(html_body: str, date_long: str) -> None:
    _smtp_send(f"SB Policy Brief \u2014 {date_long}", html_body)


def send_failure(run_date: str) -> None:
    actions_url = "https://github.com/khiran-oneill/sb-daily-digest/actions"
    html = f"""
<p style="font-family:sans-serif">
  The Springboard daily brief <strong>failed to generate</strong> on {run_date}.<br><br>
  <a href="{actions_url}">View the GitHub Actions log</a> for details.<br><br>
  You can trigger a manual re-run from that page once the issue is resolved.
</p>
"""
    _smtp_send(f"[FAILED] SB Policy Brief \u2014 {run_date}", html)


if __name__ == "__main__":
    # Quick smoke-test: python send_brief.py
    print("send_brief.py loaded OK")
