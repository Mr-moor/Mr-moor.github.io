# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from models import db, User, Admin, Transaction, Plan, Subscription, Invoice
from admin_routes import admin_bp
from tasks import process_billing_cycle
from radius_integration import grant_wifi_access
from mpesa_clients import MpesaClient
from flask import jsonify, request
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# ----------------------------
# Basic Configuration
# ----------------------------
app.secret_key = "supersecretkey"  # change in production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///wifinite.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


# ----------------------------
# Home Route
# ----------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register_admin', methods=['GET', 'POST'])
def register_admin():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        
        new_admin = Admin(name=name, phone=phone, password_hash=hashed_pw, role='Admin')
        db.session.add(new_admin)
        db.session.commit()
        flash("✅ Admin registered successfully. You can now log in.", "success")
        return render_template('admin_login.html')
    
    return render_template('admin_register.html')

# ----------------------------
# User Registration
# ----------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if not all([name, phone, password]):
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if User.query.filter_by(phone=phone).first():
            flash('Phone number already registered.', 'warning')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        new_user = User(name=name, phone=phone, password_hash=hashed_pw, role='User')
        db.session.add(new_user)
        db.session.commit()

        flash('✅ Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/support', methods=['GET'])
def support_page():
    return render_template('support.html')

@app.route('/send_support_email', methods=['POST'])
def send_support_email():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    message = data.get('message')

    try:
        sender_email = " "  # Your Gmail
        app_password = "YOUR_APP_PASSWORD"       # Use App Password, not your login
        receiver_email = "onyimbodancan@gmail.com"  # Where you receive support emails

        subject = f"New Support Message from {name}"
        body = f"From: {name} <{email}>\n\nMessage:\n{message}"

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = receiver_email

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())

        return jsonify({"message": "✅ Message sent successfully!"})

    except Exception as e:
        print("Error:", e)
        return jsonify({"message": "❌ Failed to send message. Try again later."})
    return redirect(url_for('support_page'))

# ----------------------------
# User Login
# ----------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(phone=phone).first()
        admin = Admin.query.filter_by(phone=phone).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.name
            session['role'] = 'User'
            flash('✅ Login successful!', 'success')
            return redirect(url_for('user_home'))

        elif admin and check_password_hash(admin.password_hash, password):
            session['admin_id'] = admin.id
            session['admin_name'] = admin.name
            session['role'] = 'Admin'
            flash('✅ Admin login successful!', 'success')
            return redirect(url_for('admin_bp.admin_dashboard'))

        else:
            flash('❌ Invalid phone number or password.', 'danger')

    return render_template('login.html')


# ----------------------------
# User Dashboard
# ----------------------------
@app.route('/user_home')
def user_home():
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    subscription = Subscription.query.filter_by(user_id=user.id).first()
    plans = Plan.query.all()
    txns = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.timestamp.desc()).all()

    return render_template('user_home.html', user=user, subscription=subscription, plans=plans, txns=txns)

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


# ----------------------------
# User Logout
# ----------------------------
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ----------------------------
# Generate Invoices (Admin)
# ----------------------------


@app.route('/generate_invoice/<int:user_id>', methods=['POST'])
def generate_invoice(user_id):
    if session.get('role') != 'Admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('admin_bp.admin_login'))

    amount = request.form.get('amount')
    due_date = request.form.get('due_date')

    new_invoice = Invoice(
        user_id=user_id,
        amount=float(amount),
        status='Unpaid',
        generated_at=datetime.utcnow(),
        due_date=datetime.strptime(due_date, '%Y-%m-%d')
    )
    db.session.add(new_invoice)
    db.session.commit()

    flash('✅ Invoice generated successfully.', 'success')
    return redirect(url_for('admin_bp.admin_dashboard'))


# ----------------------------
# Automated Billing
# ----------------------------
@app.route('/run_billing')
def run_billing():
    if session.get('role') != 'Admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('admin_bp.admin_login'))

    try:
        process_billing_cycle()
        flash('✅ Billing cycle executed successfully!', 'success')
    except Exception as e:
        flash(f'❌ Error running billing: {e}', 'danger')

    return redirect(url_for('admin_bp.admin_dashboard'))

@admin_bp.route('/add_plan', methods=['GET', 'POST'])
def add_plan():
    if request.method == 'POST':
        name = request.form['name']
        speed = request.form['speed']
        price = request.form['price']
        download_speed = request.form.get('download_speed', speed)
        upload_speed = request.form.get('upload_speed', speed)
        connection_type = request.form['connection_type']
        data_quota = request.form.get('data_quota', 0)  # default to 0 if not provided
        # create and save new plan
        new_plan = Plan(name=name, speed=speed, price=price,download_speed=download_speed,
            upload_speed=upload_speed,data_quota=float(data_quota), connection_type=connection_type,billing_type='flat')
        db.session.add(new_plan)
        db.session.commit()

        flash('Plan added successfully!', 'success')
        return redirect(url_for('admin_bp.admin_dashboard'))  # go back to dashboard after saving

    # GET request: show the form
    return render_template('add_plan.html')


# ----------------------------
# M-PESA Payment Integration
# ----------------------------
@app.route('/initiate_payment', methods=['POST'])
def initiate_payment():
    # Ensure user is logged in
    if 'user_id' not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    plan_id = request.form.get('plan_id')

    if not plan_id:
        flash("❌ No plan selected.", "danger")
        return redirect(url_for('user_home'))

    # Fetch plan from DB
    plan = Plan.query.get(plan_id)
    if not plan:
        flash("❌ Invalid plan selected.", "danger")
        return redirect(url_for('user_home'))

    # Get the amount directly from plan's price
    amount = float(plan.price)

    # Format phone number correctly
    phone = user.phone.strip()
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif phone.startswith('+'):
        phone = phone.replace('+', '')

    # Create transaction record
    transaction = Transaction(
        user_id=user.id,
        phone=phone,
        amount=amount,
        status='Pending',
        plan_id=plan.id
    )
    db.session.add(transaction)
    db.session.commit()

    print(f"📲 Sending STK push to {phone} for Ksh {amount}, transaction ID: {transaction.id}")

    # Initialize M-PESA client and send STK push
    mpesa = MpesaClient()
    try:
        mpesa.stk_push(phone, amount, transaction.id)
        flash(f"📲 STK push sent for '{plan.name}' (Ksh {amount}). Check your phone.", "success")
    except Exception as e:
        print("M-PESA ERROR:", e)
        flash("❌ Failed to initiate payment. Please try again later.", "danger")

    return redirect(url_for('user_home'))


@app.route('/callback', methods=['POST'])
def mpesa_callback():
    data = request.get_json()
    print("📩 Callback received:", data)

    stk_data = data.get('Body', {}).get('stkCallback', {})
    if stk_data.get('ResultCode') == 0:
        metadata = stk_data['CallbackMetadata']['Item']
        phone = next((i['Value'] for i in metadata if i['Name'] == 'PhoneNumber'), None)
        amount = next((i['Value'] for i in metadata if i['Name'] == 'Amount'), None)
        receipt = next((i['Value'] for i in metadata if i['Name'] == 'MpesaReceiptNumber'), None)

        txn = Transaction.query.filter_by(phone=phone, status='Pending').order_by(Transaction.timestamp.desc()).first()
        if txn:
            txn.status = 'Completed'
            txn.mpesa_receipt = receipt
            txn.raw_callback = str(data)
            db.session.commit()

        if phone:
            grant_wifi_access(username=str(phone))
            print(f"✅ WiFi access granted for {phone}")

    else:
        print("❌ Payment failed or incomplete callback")

    return "OK"

# ----------------------------
# Error Handlers
# ----------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    flash('Internal server error. Please try again later.', 'danger')
    return render_template('500.html'), 500

@admin_bp.route("/revenue")
def view_revenue():
    invoices = Invoice.query.filter_by(status="Paid").all()
    return render_template("revenue.html", invoices=invoices)


@admin_bp.route("/unpaid")
def view_unpaid():
    invoices = Invoice.query.filter_by(status="Unpaid").all()
    return render_template("unpaid.html", invoices=invoices)


@admin_bp.route("/overdue")
def view_overdue():
    now = datetime.utcnow()
    invoices = Invoice.query.filter(Invoice.due_date < now, Invoice.status != "Paid").all()
    return render_template("overdue.html", invoices=invoices)


@admin_bp.route("/users")
def view_users():
    users = User.query.all()
    return render_template("users.html", users=users)

import csv
from io import StringIO
from flask import Response

@admin_bp.route("/overdue/download")
def download_overdue():
    overdue = Invoice.query.filter(
        Invoice.status != "Paid",
        Invoice.due_date < datetime.utcnow()
    ).all()

    si = StringIO()
    writer = csv.writer(si)

    # CSV Header
    writer.writerow(["ID", "User", "Plan", "Amount", "Generated", "Due Date", "Status"])

    # CSV Data
    for inv in overdue:
        writer.writerow([
            inv.id,
            inv.user.name if inv.user else "—",
            inv.subscription.plan.name if inv.subscription else "—",
            inv.amount,
            inv.generated_at.strftime("%Y-%m-%d"),
            inv.due_date.strftime("%Y-%m-%d"),
            "Overdue"
        ])

    output = si.getvalue()
    si.close()

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=overdue_invoices.csv"}
    )
@admin_bp.route("/recent-invoices")
def view_recent_invoices():
    invoices = Invoice.query.order_by(Invoice.generated_at.desc()).all()
    return render_template("recent_invoices.html", invoices=invoices)


@admin_bp.route("/active-subscriptions")
def view_active_subscriptions():
    subs = Subscription.query.filter_by(active=True).all()  # or your logic
    return render_template("active_subscriptions.html", subscriptions=subs)


@admin_bp.route("/bandwidth-control")
def view_bandwidth_control():
    users = User.query.all()  # or only users with a plan/bandwidth
    return render_template("bandwith_control.html", users=users)

@admin_bp.route("/dashboard")
def dashboard():
    invoices = Invoice.query.all()
    overdue_invoices = Invoice.query.filter(Invoice.status != "Paid", Invoice.due_date < datetime.utcnow()).all()
    unpaid_invoices = Invoice.query.filter_by(status="Unpaid").all()
    users = User.query.all()

    total_active_subscriptions = Subscription.query.filter_by(active=True).count()

    total_revenue = sum(inv.amount for inv in invoices if inv.status == "Paid")

    return render_template("dashboard.html",
                           invoices=invoices,
                           overdue_invoices=overdue_invoices,
                           unpaid_invoices=unpaid_invoices,
                           users=users,
                           total_active_subscriptions=total_active_subscriptions,
                           total_revenue=total_revenue)


# ----------------------------
# Initialize Database
# ----------------------------
with app.app_context():
    db.create_all()

app.register_blueprint(admin_bp)

# ----------------------------
# Run
# ----------------------------
if __name__ == '__main__':
    app.run(debug=True)
