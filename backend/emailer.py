"""
Automated emailing of test links to shortlisted candidates.

Per the assignment constraint ("candidates must use their own email
service"), this uses standard SMTP with the recruiter's own Gmail account
and an App Password (NOT the Gmail API, no OAuth needed for this part —
simplest path that satisfies "send emails from your own account").

Credentials are read from environment variables so they are never hardcoded:
  SENDER_EMAIL, SENDER_APP_PASSWORD
"""

import os
import smtplib
import json
from email.mime.text import MIMEText

from db import get_conn

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD", "")
TEST_LINK = os.environ.get("TEST_LINK", "https://forms.gle/your-test-form-link")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _send_email(to_email: str, subject: str, body: str) -> bool:
    if not SENDER_EMAIL or not SENDER_APP_PASSWORD:
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"Email send failed for {to_email}: {e}")
        return False


def send_test_links_to_shortlisted(top_n: int = 5) -> dict:
    conn = get_conn()
    rows = conn.execute(
        """SELECT s_no, name, email FROM candidates
           WHERE status = 'shortlisted_pending_test'
           ORDER BY final_score DESC LIMIT ?""",
        (top_n,),
    ).fetchall()

    sent, failed = 0, 0
    for s_no, name, email in rows:
        subject = "You've been shortlisted — Next step: Online Assessment"
        body = (
            f"Hi {name},\n\n"
            f"Congratulations! Based on our initial AI-assisted screening, you've been "
            f"shortlisted for the next stage of our hiring process.\n\n"
            f"Please complete the following assessment within 48 hours:\n{TEST_LINK}\n\n"
            f"This includes a logical aptitude section and a coding test.\n\n"
            f"Best regards,\nHiring Team"
        )
        ok = _send_email(email, subject, body)
        if ok:
            conn.execute("UPDATE candidates SET status='test_sent' WHERE s_no=?", (s_no,))
            sent += 1
        else:
            failed += 1

    conn.commit()
    conn.close()
    return {"sent": sent, "failed": failed, "total_attempted": len(rows)}
