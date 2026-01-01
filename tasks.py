from datetime import datetime, timedelta
from models import Subscription, Invoice, User, Plan
from mpesa_clients import MpesaClient
from radius_integration import disable_user_access, enable_user_access

mpesa = MpesaClient()


def calculate_usage_charges(subscription):
    """Calculates additional charges for data/time-based plans."""
    plan = subscription.plan
    if plan.billing_type == 'data' and plan.rate_per_gb:
        used_gb = subscription.usage_bytes / (1024 ** 3)
        extra_charge = max(0, used_gb * plan.rate_per_gb)
        return round(extra_charge, 2)
    elif plan.billing_type == 'time' and plan.rate_per_hour:
        extra_charge = subscription.usage_hours * plan.rate_per_hour
        return round(extra_charge, 2)
    return 0.0


def calculate_prorated_charge(subscription, old_plan, new_plan):
    """Handles mid-cycle plan changes and computes pro-rated billing."""
    if not subscription.end_at:
        return 0.0

    now = datetime.utcnow()
    total_days = (subscription.end_at - subscription.start_at).days or 1
    remaining_days = max((subscription.end_at - now).days, 0)
    remaining_ratio = remaining_days / total_days

    old_plan_value = old_plan.price * remaining_ratio
    prorated_charge = max(0, new_plan.price - old_plan_value)
    return round(prorated_charge, 2)


def process_billing_cycle(app=None, db=None):
    """
    Automated billing process:
      - Flat, data-based, and time-based billing
      - Pro-rated mid-cycle billing
      - M-Pesa STK push auto-renew
      - Access control (Hotspot/PPPoE)
    """

    # Allow running without explicit app/db args if already in app context
    if not app or not db:
        from flask import current_app
        from extensions import db as _db
        app = current_app
        db = _db

    with app.app_context():
        now = datetime.utcnow()
        subscriptions = Subscription.query.filter_by(active=True).all()

        for sub in subscriptions:
            plan = sub.plan
            user = sub.user

            # 1️⃣ Disable expired subscriptions
            if sub.end_at and sub.end_at < now:
                sub.active = False
                try:
                    disable_user_access(user.phone, plan.connection_type)
                    print(f"[INFO] Disabled expired subscription for {user.phone} ({plan.name})")
                except Exception as e:
                    print(f"[ERROR] Failed to disable access for {user.phone}: {e}")
                continue

            # 2️⃣ Handle pro-rated billing
            if sub.mid_cycle_plan_change:
                old_plan = plan
                new_plan = sub.plan
                prorated_charge = calculate_prorated_charge(sub, old_plan, new_plan)
                if prorated_charge > 0:
                    invoice = Invoice(
                        user_id=user.id,
                        subscription_id=sub.id,
                        amount=prorated_charge,
                        generated_at=now,
                        due_date=now + timedelta(days=3),
                        status='Unpaid'
                    )
                    db.session.add(invoice)
                    sub.mid_cycle_plan_change = False
                    db.session.commit()
                    print(f"[INFO] Pro-rated invoice generated for {user.phone}: {prorated_charge} KES")

            # 3️⃣ Generate regular invoices
            if not sub.last_billed_at or (now - sub.last_billed_at).days >= plan.duration_days:
                base_amount = plan.price
                extra_charges = calculate_usage_charges(sub)
                total_due = base_amount + extra_charges

                invoice = Invoice(
                    user_id=user.id,
                    subscription_id=sub.id,
                    amount=total_due,
                    generated_at=now,
                    due_date=now + timedelta(days=3),
                    status='Unpaid'
                )
                db.session.add(invoice)

                sub.last_billed_at = now
                sub.end_at = now + timedelta(days=plan.duration_days)
                db.session.commit()

                print(f"[INFO] Invoice created for {user.phone}: {total_due} KES (base: {base_amount}, extra: {extra_charges})")

                # 4️⃣ Attempt auto-renew
                if sub.auto_renew:
                    try:
                        print(f"[INFO] Initiating auto-renew for {user.phone}")
                        response = mpesa.stk_push(user.phone, total_due, invoice.id)
                        if response.get("ResponseCode") == "0":
                            enable_user_access(user.phone, plan.connection_type)
                            invoice.status = "Paid"
                            db.session.commit()
                            print(f"[SUCCESS] Auto-renew successful for {user.phone}")
                        else:
                            print(f"[WARN] STK push failed for {user.phone}: {response}")
                    except Exception as e:
                        print(f"[ERROR] Auto-renew failed for {user.phone}: {e}")

        print(f"[DONE] Billing cycle processed at {now}")
