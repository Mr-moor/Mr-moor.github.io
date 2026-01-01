# billing.py
import math
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from models import db, User, Plan, Subscription, Usage, Invoice

# ---- Utility: rounding money ----
def money(v):
    return float(Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

# ---- Billing period helpers ----
def next_cycle_start(dt: datetime, cycle: str) -> datetime:
    if cycle == 'daily':
        return (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if cycle == 'weekly':
        # week start next week's Monday
        days_until_monday = (7 - dt.weekday()) % 7
        return (dt + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    # default monthly: next month first day
    year = dt.year + (1 if dt.month == 12 else 0)
    month = 1 if dt.month == 12 else dt.month + 1
    return datetime(year, month, 1, tzinfo=dt.tzinfo)

def cycle_delta(cycle: str, dt: datetime):
    if cycle == 'daily':
        return timedelta(days=1)
    if cycle == 'weekly':
        return timedelta(weeks=1)
    # approximate monthly as month-end → use helper
    # We'll compute period end separately for month
    return None

def period_range(start: datetime, cycle: str):
    """Return (period_start, period_end) given start."""
    if cycle == 'daily':
        end = start + timedelta(days=1)
    elif cycle == 'weekly':
        end = start + timedelta(weeks=1)
    else:
        # monthly: end = start + month length
        year = start.year + (1 if start.month == 12 else 0)
        month = 1 if start.month == 12 else start.month + 1
        end = datetime(year, month, 1, tzinfo=start.tzinfo)
    return start, end

# ---- Proration calculation ----
def prorated_amount(full_price: float, cycle: str, from_dt: datetime, to_dt: datetime=None):
    """Return prorated portion of full_price for remaining time in cycle.
       If to_dt is None, compute from from_dt to cycle end."""
    start = from_dt
    if to_dt is None:
        # determine period end for the current cycle containing from_dt
        if cycle == 'daily':
            end = (from_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif cycle == 'weekly':
            # end: next monday 00:00
            days_until_monday = (7 - from_dt.weekday()) % 7
            end = (from_dt + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            if end <= from_dt:
                end += timedelta(weeks=1)
        else:
            # monthly: end = first of next month
            year = from_dt.year + (1 if from_dt.month == 12 else 0)
            month = 1 if from_dt.month == 12 else from_dt.month + 1
            end = datetime(year, month, 1, tzinfo=from_dt.tzinfo)
    else:
        end = to_dt

    # total seconds in period and used seconds
    # find period_start for the cycle (start of current cycle)
    if cycle == 'daily':
        period_start = from_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=1)
    elif cycle == 'weekly':
        # find last monday 00:00
        monday = from_dt - timedelta(days=from_dt.weekday())
        period_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(weeks=1)
    else:
        period_start = from_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year = period_start.year + (1 if period_start.month == 12 else 0)
        month = 1 if period_start.month == 12 else period_start.month + 1
        period_end = datetime(year, month, 1, tzinfo=period_start.tzinfo)

    total = (period_end - period_start).total_seconds()
    charge_seconds = (end - from_dt).total_seconds()
    ratio = max(0.0, min(1.0, charge_seconds / total))
    return money(full_price * ratio), ratio

# ---- Usage aggregation ----
def usage_for_subscription(subscription: Subscription, period_start: datetime, period_end: datetime):
    # sum rx+tx bytes for that subscription and period
    q = Usage.query.filter(
        Usage.subscription_id == subscription.id,
        Usage.timestamp >= period_start,
        Usage.timestamp < period_end
    )
    total_bytes = 0
    for u in q:
        total_bytes += (u.rx_bytes or 0) + (u.tx_bytes or 0)
    return total_bytes

# ---- Main billing function ----
def generate_invoices_for_date(run_date: datetime=None):
    """Top-level driver invoked by scheduler nightly.
       This will:
         - iterate active subscriptions
         - determine if billing is due for their cycle
         - compute price (prorated if needed)
         - include usage fees if plan.price_per_gb set
         - create Invoice rows
    """
    now = run_date or datetime.now(timezone.utc)
    invoices_created = []

    subs = Subscription.query.filter(Subscription.active == True).all()
    for sub in subs:
        plan = sub.plan
        # determine last billed or subscription start
        last_billed = sub.last_billed_at or sub.start_at
        # compute next billing point depending on cycle
        # We will bill for any completed cycles since last_billed
        # For monthly we bill at start of cycle; implement a conservative approach:
        needs_billing = False
        period_start = None
        period_end = None

        if plan.billing_cycle == 'daily':
            # bill for each day boundary passed since last_billed
            # bill on midnight passes
            next_boundary = (last_billed + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            if now >= next_boundary:
                period_start = next_boundary - timedelta(days=1)
                period_end = next_boundary
                needs_billing = True

        elif plan.billing_cycle == 'weekly':
            # find week boundary (monday 00:00) after last_billed
            # compute last monday after last_billed
            monday_after = (last_billed - timedelta(days=last_billed.weekday())).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(weeks=1)
            if now >= monday_after:
                period_start = monday_after - timedelta(weeks=1)
                period_end = monday_after
                needs_billing = True

        else:  # monthly
            # compute first-of-next-month after last_billed
            year = last_billed.year + (1 if last_billed.month == 12 else 0)
            month = 1 if last_billed.month == 12 else last_billed.month + 1
            first_next_month = datetime(year, month, 1, tzinfo=last_billed.tzinfo)
            if now >= first_next_month:
                # period is from first_of_month_containing(last_billed) to first_next_month
                period_start = last_billed.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                period_end = first_next_month
                needs_billing = True

        # If subscription started mid-cycle and we are billing first partial period, proration applies
        if needs_billing and period_start and period_end:
            # base charge: plan.price for full cycle
            base_amount = plan.price
            # If subscription started after period_start => prorate for the active duration.
            bill_start = max(sub.start_at, period_start)
            # If user ended subscription before period_end => prorate for partial period
            bill_end = min(sub.end_at, period_end) if sub.end_at else period_end

            # prorate portion for cycle if not full
            if bill_start > period_start or bill_end < period_end:
                # calculate prorated amount for active seconds inside this cycle
                prorate_amount, ratio = prorated_amount(base_amount, plan.billing_cycle, bill_start, bill_end)
            else:
                prorate_amount, ratio = money(base_amount), 1.0

            usage_amount = 0.0
            if plan.price_per_gb:
                total_bytes = usage_for_subscription(sub, period_start, period_end)
                gb_used = total_bytes / (1024**3)
                usage_amount = money(gb_used * plan.price_per_gb)

            total = money(prorate_amount + usage_amount)
            invoice = Invoice(
                user_id=sub.user_id,
                subscription_id=sub.id,
                period_start=period_start,
                period_end=period_end,
                amount=total,
                details=json.dumps({
                    'plan_price': base_amount,
                    'prorated_price': prorate_amount,
                    'proration_ratio': ratio,
                    'usage_bytes': int(total_bytes) if plan.price_per_gb else 0,
                    'usage_charge': usage_amount
                })
            )
            db.session.add(invoice)
            # update last_billed_at to period_end
            sub.last_billed_at = period_end
            db.session.commit()
            invoices_created.append(invoice)
            # placeholder: optionally call immediate charging
            # charge_customer(sub.user, invoice)  <-- integrate mpesa here
    return invoices_created

# ---- Pro-rate when changing plan mid-cycle ----
def change_subscription_plan(subscription: Subscription, new_plan: Plan, change_time: datetime=None):
    """
    Apply proration: when user switches plan mid-cycle we:
      - generate an invoice for the old plan prorated up to change_time (if not already billed)
      - start a new subscription period on change_time (with last_billed_at updated)
    """
    now = change_time or datetime.now(timezone.utc)
    old_plan = subscription.plan

    # determine current cycle's period_start and period_end
    ps, pe = period_range(subscription.start_at, old_plan.billing_cycle)
    # compute prorated charge for old plan from last_billed_at (or start) up to now
    last_billed = subscription.last_billed_at or subscription.start_at
    if now <= last_billed:
        # nothing to bill
        pass
    else:
        prorate_amount, ratio = prorated_amount(old_plan.price, old_plan.billing_cycle, now)
        # NOTE: for correctness compute portion from last_billed -> now within current cycle
        # Simpler: compute proportion of remaining cycle billed to new_plan and charge old plan for used seconds
        # We will compute used portion:
        #used_amount = full_price * used_seconds / total_seconds
        #used_seconds = (now - period_start).total_seconds()
        #total_seconds = (period_end - period_start).total_seconds()
        #used_amount = old_plan.price * (used_seconds/total_seconds)
        # We'll implement used_amount:
        period_start = ps
        period_end = pe
        used_seconds = (now - period_start).total_seconds()
        total_seconds = (period_end - period_start).total_seconds()
        used_ratio = max(0.0, min(1.0, used_seconds / total_seconds))
        used_amount = money(old_plan.price * used_ratio)

        invoice = Invoice(
            user_id=subscription.user_id,
            subscription_id=subscription.id,
            period_start=period_start,
            period_end=now,
            amount=used_amount,
            details=json.dumps({
                'note': 'prorated for mid-cycle change (old plan)',
                'used_ratio': used_ratio
            })
        )
        db.session.add(invoice)
        db.session.commit()

    # switch plan
    subscription.plan_id = new_plan.id
    # set last_billed_at to now so new plan's billing starts fresh from now
    subscription.last_billed_at = now
    db.session.commit()
    # optionally create immediate invoice for new plan prorated for remainder of cycle (if you prefer)
    # The generate_invoices_for_date will bill at next boundary (or you can create a prorated invoice explicitly here)
    return subscription
