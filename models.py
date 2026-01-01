# models.py
from extensions import db
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(200), nullable=True)
    password_hash= db.Column(db.String(200), nullable=False)
    data_used = db.Column(db.Float, default=0.0)  # in GB
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(50), default="user")  # user or admin
    subscriptions = db.relationship('Subscription', back_populates='user', cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    tickets = db.relationship('Ticket', backref='user', lazy=True)
    invoices = db.relationship('Invoice', backref='user', lazy=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))  # ✅ add this
    plan = db.relationship('Plan', backref='users', lazy=True)  # ✅ add this

    def remaining_data(self):
        if self.plan:
            data_used = sum(invoice.data_used for invoice in self.invoices)
            return self.plan.data_limit - used_data
        return 0.0
    
    def verify_password(self, password):
        
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def remaining_data(self):
        if self.plan:
            return max(self.plan.data_quota - self.data_used, 0)
        return 0
    
class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Float, nullable=False)
    speed = db.Column(db.String(50), nullable=True)
    duration_days = db.Column(db.Integer, nullable=False, default=30)
    connection_type = db.Column(db.String(20), nullable=False)  # hotspot, pppoe, static_ip
    billing_type = db.Column(db.String(20), default='flat')  # flat, data, time
    rate_per_gb = db.Column(db.Float, nullable=True)  # for data-based plans
    rate_per_hour = db.Column(db.Float, nullable=True)  # for time-based plans
    data_bytes = db.Column(db.BigInteger, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    download_speed = db.Column(db.Float, nullable=True)  # in Mbps
    upload_speed = db.Column(db.Float, nullable=True)    # in Mbps
    data_quota = db.Column(db.Float, nullable=True)
    subscriptions = db.relationship('Subscription', back_populates='plan', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Plan {self.name}>'
    
class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))
    status = db.Column(db.String(20), default='pending')  
    start_at = db.Column(db.DateTime, default=datetime.utcnow)
    end_at = db.Column(db.DateTime, nullable=True)
    last_billed_at = db.Column(db.DateTime, nullable=True)
    active = db.Column(db.Boolean, default=True)
    auto_renew = db.Column(db.Boolean, default=False)
    usage_bytes = db.Column(db.BigInteger, default=0)
    usage_hours = db.Column(db.Float, default=0)
    mid_cycle_plan_change = db.Column(db.Boolean, default=False)

    # Removed user = db.relationship('User', lazy=True)
    plan = db.relationship('Plan', back_populates='subscriptions')
    usages = db.relationship('Usage', backref='subscription', lazy=True)
    invoices = db.relationship('Invoice', back_populates='subscription')
    user = db.relationship('User', back_populates='subscriptions')
    plan = db.relationship('Plan')
    def days_remaining(self):
        if not self.end_at:
            return None
        delta = self.end_at - datetime.utcnow()
        return max(delta.days, 0)

    def prorated_amount(self, new_plan_price):
        if not self.end_at:
            return new_plan_price

        remaining_days = (self.end_at - datetime.utcnow()).days
        total_days = (self.end_at - self.start_at).days or 1
        unused_ratio = remaining_days / total_days
        return round(new_plan_price * unused_ratio, 2)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(40), default='Pending')  # Pending, Completed, Failed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    mpesa_receipt = db.Column(db.String(100), nullable=True)
    merchant_request_id = db.Column(db.String(100), nullable=True)
    checkout_request_id = db.Column(db.String(100), nullable=True)
    raw_callback = db.Column(db.Text, nullable=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'), nullable=True)

    plan = db.relationship('Plan', lazy=True)


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='Open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Usage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    rx_bytes = db.Column(db.BigInteger, default=0)
    tx_bytes = db.Column(db.BigInteger, default=0)


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'))
    subscription = db.relationship('Subscription', back_populates='invoices')
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default='Unpaid')  # Unpaid, Paid, Overdue
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=3))
    paid_at = db.Column(db.DateTime, nullable=True)
    
    def mark_paid(self):
        self.status = 'Paid'
        self.paid_at = datetime.utcnow()
        invoices = Invoice.query.filter_by(user_id=session['user_id']).all()
        return render_template('invoice.html', invoices=invoices)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='Admin')

    def __init__(self, name, phone, password_hash, role='Admin'):
        self.name = name
        self.phone = phone
        self.password_hash = password_hash  # already hashed in app.py
        self.role = role
