import imaplib, email, smtplib, os, json
from email.mime.text import MIMEText
from email.utils import formatdate, parsedate_to_datetime
from dotenv import load_dotenv
from datetime import datetime, timedelta

# ---------------- Config ----------------
STATE_PATH = "state.json"
THRESHOLD = 4

load_dotenv()

# Monitored inbox (Account A)
MONITOR_EMAIL = os.getenv("MONITOR_EMAIL")
MONITOR_PASS = os.getenv("MONITOR_APP_PASSWORD")
MONITOR_IMAP = os.getenv("MONITOR_IMAP_SERVER", "imap.gmail.com")
MONITOR_PORT = int(os.getenv("MONITOR_IMAP_PORT", 993))

# Alert sender (Account B)
ALERT_EMAIL_SENDER = os.getenv("ALERT_EMAIL_SENDER")
ALERT_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD")
ALERT_EMAIL_RECIPIENT = os.getenv("ALERT_EMAIL_RECIPIENT")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))


# ---------------- State Management ----------------
def load_state():
    if not os.path.exists(STATE_PATH):
        return {"last_check": None}
    with open(STATE_PATH, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ---------------- Email Alert ----------------
def send_alert(subject, count):
    body = f"ALERT: {count} emails received with subject '{subject}' in Bulleteconomics Gmail within the last hour."
    msg = MIMEText(body)
    msg["Subject"] = f"[ALERT] {subject}"
    msg["From"] = ALERT_EMAIL_SENDER
    msg["To"] = ALERT_EMAIL_RECIPIENT
    msg["Date"] = formatdate(localtime=True)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(ALERT_EMAIL_SENDER, ALERT_EMAIL_PASSWORD)
        server.sendmail(ALERT_EMAIL_SENDER, [ALERT_EMAIL_RECIPIENT], msg.as_string())

    print(f"✅ Alert sent for subject: {subject} ({count} emails)")


# ---------------- Gmail Checker ----------------
def check_gmail():
    state = load_state()
    last_check_str = state.get("last_check")
    last_check = datetime.fromisoformat(last_check_str) if last_check_str else datetime.now() - timedelta(hours=1)
    now = datetime.now()

    print(f"\n[{now}] Checking emails from the past 1 hour...")

    # Connect to IMAP
    mail = imaplib.IMAP4_SSL(MONITOR_IMAP, MONITOR_PORT)
    mail.login(MONITOR_EMAIL, MONITOR_PASS)
    mail.select("inbox")

    # Search all messages since yesterday (IMAP can't do hours)
    since_date = (now - timedelta(days=1)).strftime("%d-%b-%Y")
    status, data = mail.search(None, f'(SINCE "{since_date}")')

    if status != "OK":
        print("⚠️ No messages found or search failed.")
        mail.close()
        mail.logout()
        return

    mail_ids = data[0].split()
    subject_counts = {}

    for mid in mail_ids:
        status, msg_data = mail.fetch(mid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        try:
            email_date = parsedate_to_datetime(msg["Date"])
        except Exception:
            email_date = now

        # Only consider emails from the last hour
        if email_date < now - timedelta(hours=1):
            continue

        subject = msg["Subject"] or "No Subject"
        subject_counts[subject] = subject_counts.get(subject, 0) + 1

    mail.close()
    mail.logout()

    # Check threshold
    for subject, count in subject_counts.items():
        if count >= THRESHOLD:
            send_alert(subject, count)

    # Save last check time
    state["last_check"] = now.isoformat()
    save_state(state)
    print(f"✅ Completed check at {now}. Exiting...")


# ---------------- Run Once ----------------
if __name__ == "__main__":
    try:
        check_gmail()
    except Exception as e:
        print(f"❌ Error: {e}")
