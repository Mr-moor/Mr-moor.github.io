# scheduler.py
import os
from datetime import datetime, timezone
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from models import db, User, Plan, Subscription, Usage, Invoice
from billing import generate_invoices_for_date

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///billing.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def start_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=lambda: run_billing_job(app), trigger="cron", hour=0, minute=5)  # daily at 00:05
    # optional: add hourly job for usage-based microbilling
    scheduler.add_job(func=lambda: run_billing_job(app, hourly=True), trigger="cron", minute=0)  # hourly
    scheduler.start()
    print("Scheduler started")

def run_billing_job(app, hourly=False):
    with app.app_context():
        now = datetime.now(timezone.utc)
        print("Billing job running at", now.isoformat(), "hourly=", hourly)
        invoices = generate_invoices_for_date(now)
        print(f"Created {len(invoices)} invoices")
        # optionally: generate HTML invoices for each
        from invoice_utils import invoice_to_html
        for inv in invoices:
            user = User.query.get(inv.user_id)
            path = invoice_to_html(inv, user)
            print("Saved invoice HTML:", path)
            # optionally: call payment automation here

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    start_scheduler(app)
    # keep alive (simple loop)
    try:
        import time
        while True:
            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down scheduler")
