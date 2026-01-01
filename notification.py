import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
import sqlite3

# ===============================
# CONFIGURATION
# ===============================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "yourbusiness@gmail.com"
SENDER_PASSWORD = "your_app_password"  # Use App Password for Gmail

DB_PATH = "wifinity.db"  # path to your main SQLite database


# ===============================
# EMAIL UTILS
# ===============================
def send_email(to_email, subject, body):
    """Send an email message"""
    msg = EmailMessage()
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
            smtp.send_message(msg)
            print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")


# ===============================
# DATABASE HELPERS
# ===============================
def get_users():
    """Fetch all users and their billing data"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, email, next_payment_date, data_used, data_limit FROM user")
    data = cur.fetchall()
    conn.close()
    return data


# ===============================
# NOTIFICATION TASKS
# ===============================
def send_payment_reminders():
    """Send payment reminders 3 days before due date"""
    users = get_users()
    today = datetime.now().date()
    for user in users:
        user_id, name, email, next_payment, data_used, data_limit = user
        if not next_payment:
            continue
        due_date = datetime.strptime(next_payment, "%Y-%m-%d").date()
        if due_date - today == timedelta(days=3):
            subject = "⏰ Payment Reminder – WiFinity Subscription"
            body = f"""
Dear {name},

This is a friendly reminder that your WiFinity subscription will expire on {due_date}.
Please make your payment before this date to avoid service interruption.

Thank you for choosing WiFinity!
—
WiFinity Support Team
"""
            send_email(email, subject, body)


def send_usage_alerts():
    """Notify users when they reach 80% of their data limit"""
    users = get_users()
    for user in users:
        user_id, name, email, next_payment, data_used, data_limit = user
        if not data_limit or not data_used:
            continue
        if data_used >= 0.8 * data_limit:
            subject = "📊 Usage Alert – WiFinity Data Limit"
            body = f"""
Dear {name},

You’ve used {round((data_used/data_limit)*100)}% of your data plan.
Please consider upgrading or monitoring your usage.

WiFinity – Keeping you connected.
"""
            send_email(email, subject, body)


def send_service_announcement(title, message):
    """Send a general service announcement to all users"""
    users = get_users()
    for user in users:
        _, name, email, *_ = user
        subject = f"📢 WiFinity Service Update: {title}"
        body = f"""
Dear {name},

{message}

Thank you for your continued support.
—
WiFinity Team
"""
        send_email(email, subject, body)


# ===============================
# SCHEDULER
# ===============================
def start_scheduler():
    """Start background jobs"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_payment_reminders, 'interval', days=1, id='payment_reminders')
    scheduler.add_job(send_usage_alerts, 'interval', hours=6, id='usage_alerts')
    scheduler.start()
    print("🚀 Notification scheduler started.")
