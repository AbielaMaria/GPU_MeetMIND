"""
MeetMind - OTP email sender.

Sends plain SMTP mail (stdlib smtplib, no third-party service). Config is
loaded from the project-root .env, same convention as mistral_client.py.
Swapping to an official org mailbox later is just changing SMTP_USER /
SMTP_PASSWORD in .env — no code change.
"""

from email.message import EmailMessage
from pathlib import Path
import os
import smtplib

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip())
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "MeetMind").strip()


def send_otp_email(to_email: str, username: str, code: str) -> None:
    """Raises on failure — callers decide how to handle a failed send."""
    msg = EmailMessage()
    msg["Subject"] = "Your MeetMind verification code"
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"] = to_email
    msg.set_content(
        f"Hi {username},\n\n"
        f"Your MeetMind verification code is: {code}\n\n"
        "This code expires in 10 minutes. Enter it on the verification "
        "page to activate your account.\n\n"
        "If you didn't request this, you can ignore this email."
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
