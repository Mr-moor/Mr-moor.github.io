# admin_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from models import db, Admin, User, Subscription, Invoice
from tasks import process_billing_cycle

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')


# ----------------------------
# Admin Registration
# ----------------------------
@admin_bp.route('/register_admin', methods=['GET', 'POST'])
def admin_register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if not all([name, phone, password]):
            flash("All fields are required.", "danger")
            return render_template('admin_register.html')

        # Check if admin exists
        existing_admin = Admin.query.filter_by(phone=phone).first()
        if existing_admin:
            flash("Admin with that phone already exists.", "danger")
            return redirect(url_for('admin_bp.admin_register'))

        # Hash password
        hashed_pw = generate_password_hash(password)

        # Create new admin
        new_admin = Admin(
            name= name,
            phone= phone,
            password_hash=hashed_pw,
            role='Admin'  # ensure role consistency
        )

        db.session.add(new_admin)
        db.session.commit()

        flash("✅ Admin registered successfully. You can now log in.", "success")
        return redirect(url_for('admin_bp.admin_login'))

    return render_template('admin_register.html')


# ----------------------------
# Admin Login
# ----------------------------
@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        # Find admin by phone
        admin = Admin.query.filter_by(phone=phone).first()

        if not admin:
            flash("❌ No admin found with that phone number.", "danger")
            return render_template('admin_login.html')

        # Check hashed password
        if not check_password_hash(admin.password_hash, password):
            flash("❌ Invalid password.", "danger")
            return render_template('admin_login.html')

        # Successful login
        session['admin_id'] = admin.id
        session['admin_name'] = admin.name
        session['role'] = 'Admin'
        flash("✅ Login successful!", "success")

        return redirect(url_for('admin_bp.admin_dashboard'))

    return render_template('admin_login.html')


# ----------------------------
# Admin Logout
# ----------------------------
@admin_bp.route('/logout')
def admin_logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('admin_bp.admin_login'))


# ----------------------------
# Admin Dashboard
# ----------------------------
@admin_bp.route('/dashboard')
def admin_dashboard():
    if session.get('role') != 'Admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('admin_bp.admin_login'))

    invoices = Invoice.query.order_by(Invoice.generated_at.desc()).all()
    users = User.query.all()

    total_revenue = sum(inv.amount for inv in invoices if inv.status == 'Paid')
    unpaid_invoices = [inv for inv in invoices if inv.status == 'Unpaid']
    overdue_invoices = [inv for inv in invoices if inv.status == 'Unpaid' and inv.due_date < datetime.utcnow()]

    return render_template(
        'admin_dashboard.html',
        admin_name=session.get('admin_name'),
        invoices=invoices,
        users=users,
        total_revenue=total_revenue,
        unpaid_invoices=unpaid_invoices,
        overdue_invoices=overdue_invoices
    )


# ----------------------------
# Manual Billing Trigger
# ----------------------------
@admin_bp.route('/billing/run')
def run_billing():
    if session.get('role') != 'Admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('admin_bp.admin_login'))

    try:
        process_billing_cycle()
        flash('✅ Billing cycle executed successfully!', 'success')
    except Exception as e:
        flash(f'❌ Error running billing cycle: {e}', 'danger')

    return redirect(url_for('admin_bp.admin_dashboard'))


# ----------------------------
# Mark Invoice as Paid
# ----------------------------
@admin_bp.route('/invoice/<int:invoice_id>/mark_paid')
def mark_invoice_paid(invoice_id):
    if session.get('role') != 'Admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('admin_bp.admin_login'))

    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = 'Paid'
    db.session.commit()

    flash(f'✅ Invoice #{invoice.id} marked as paid.', 'success')
    return redirect(url_for('admin_bp.admin_dashboard'))


# ----------------------------
# Dashboard Data API (JSON)
# ----------------------------
@admin_bp.route('/api/dashboard_data')
def dashboard_data():
    if session.get('role') != 'Admin':
        return jsonify({"error": "Unauthorized"}), 401

    total_users = User.query.count()
    active_subs = Subscription.query.filter_by(active=True).count()
    total_revenue = db.session.query(db.func.sum(Invoice.amount)).scalar() or 0
    unpaid_invoices = Invoice.query.filter_by(status='Unpaid').count()

    return jsonify({
        "total_users": total_users,
        "active_subscriptions": active_subs,
        "total_revenue": total_revenue,
        "unpaid_invoices": unpaid_invoices,
    })
from flask import Blueprint, render_template
from models import Invoice  # if you have an Invoice model


# ----------------------------
# View Invoices (Admin + User)
# ----------------------------
@admin_bp.route('/invoices', methods=['GET'])
def view_invoices():
    role = session.get('role')
    user_id = session.get('user_id')
    admin_id = session.get('admin_id')

    # Admin: can view all invoices
    if role == 'Admin' and admin_id:
        invoices = Invoice.query.order_by(Invoice.generated_at.desc()).all()
        title = "All User Invoices"

    # Regular user: can only view their own invoices
    elif role == 'User' and user_id:
        invoices = Invoice.query.filter_by(user_id=user_id).order_by(Invoice.generated_at.desc()).all()
        title = "My Invoices"

    else:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('admin_bp.admin_login'))

    return render_template('invoice_list.html', invoices=invoices, title=title)


# ----------------------------
# View Invoices by User (Admin Only)
# ----------------------------
@admin_bp.route('/invoices/<int:user_id>', methods=['GET'])
def view_invoices_by_user(user_id):
    # Ensure only admins can access this
    if session.get('role') != 'Admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('admin_bp.admin_login'))

    # Fetch invoices for that user
    invoices = Invoice.query.filter_by(user_id=user_id).order_by(Invoice.generated_at.desc()).all()
    user = User.query.get(user_id)

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('admin_bp.view_invoices'))

    title = f"Invoices for {user.name}"

    return render_template('invoice_list.html', invoices=invoices, title=title, user=user)

@admin_bp.route('/debug_admins')
def debug_admins():
    admins = Admin.query.all()
    data = [
        {"id": a.id, "name": a.name, "phone": a.phone}
        for a in admins
    ]
    return jsonify(data)


