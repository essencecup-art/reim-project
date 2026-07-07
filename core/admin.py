import datetime

from flask import Blueprint, render_template, jsonify, flash, redirect, url_for, session, request
from core.models import Order, User
from core.extensions import db
from functools import wraps

# Split into separate blueprint contexts
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
staff_bp = Blueprint('staff', __name__, url_prefix='/staff')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user or not user.get('is_admin'):
            flash("Unauthorized access. Management clearance required.", "error")
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        # 🔑 PERMISSION CHECK: Let them through if they are EITHER staff OR admin
        if not user or (not user.get('is_staff') and not user.get('is_admin')):
            flash("Unauthorized access. Staff credentials required.", "error")
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function

# =====================================================================
# 👑 OWNER FINANCIAL ENVIRONMENT (admin_bp)
# =====================================================================

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Purely financial and high-level tracking for the owner."""
    all_orders = Order.query.order_by(Order.updated_at.desc()).all()
    
    # 🗓️ Get the current calendar matrix context
    now = datetime.utcnow()
    current_year = now.year
    current_month = now.month
    
    # 💰 Calculate All-Time Gross Sales (excluding cancellations)
    gross_revenue = sum(order.total_amount for order in all_orders if order.status != 'Cancelled')
    
    # 📉 NEW: Calculate Auto-Resetting Monthly Sales 
    monthly_revenue = sum(
        order.total_amount 
        for order in all_orders 
        if order.status != 'Cancelled'
        and order.created_at.year == current_year
        and order.created_at.month == current_month
    )
    
    pending_count = sum(1 for order in all_orders if order.status not in ['Cancelled', 'Paid'])
    
    return render_template(
        'admin_dashboard.html', 
        orders=all_orders,
        revenue=gross_revenue,
        monthly_revenue=monthly_revenue,  # 👈 Pass this cleanly to your template parameters
        pending=pending_count,
        total_orders_count=len(all_orders)
    )


# =====================================================================
# 🍳 KITCHEN LINE ENVIRONMENT (staff_bp)
# =====================================================================

@staff_bp.route('/kitchen')
@staff_required
def kitchen_feed():
    """Operational ticket monitor view for the cooking crew (No financial data)."""
    # Pull only cooking tickets that need fulfillment
    active_tickets = Order.query.filter(Order.status.notin_(['Cancelled', 'Paid'])).order_by(Order.created_at.asc()).all()
    return render_template('kitchen_feed.html', orders=active_tickets)


# =====================================================================
# 📡 CLEANED SHARED API PIPELINE
# =====================================================================

@admin_bp.route('/api/orders/stream')
@admin_required
def orders_stream():
    """API endpoint providing the live background polling data stream."""
    orders = Order.query.order_by(Order.status.desc(), Order.created_at.desc()).all()
    
    orders_data = []
    for o in orders:
        orders_data.append({
            'id': o.id,
            'table': o.table_number if o.table_number else "00",
            'description': o.description,
            'status': o.status,
            'payment_method': o.payment_method,
            'amount': f"${o.total_amount / 100:.2f}",
            'time': o.created_at.strftime('%I:%M %p')
        })
        
    return jsonify({
        'orders': orders_data,
        'revenue': f"${sum(o.total_amount for o in orders) / 100:.2f}",
        'pending': sum(1 for o in orders if o.status not in ['Cancelled', 'Paid'])
    })

@staff_bp.route('/api/orders/<int:order_id>/update', methods=['POST'])
@staff_required
def update_order_status(order_id):
    """Allows staff or admin to shift an order state dynamically on the line."""
    data = request.json
    if not data or 'chef_status' not in data:
        return jsonify({'error': 'Invalid payload data.'}), 400
    chef_status = data.get('chef_status')

    order = Order.query.with_for_update().get(order_id)
    if not order:
        return jsonify({'error': 'Order resource not found.'}), 404
    
    if order.status in ['Cancelled', 'Paid'] and chef_status not in ['Cancelled', 'Paid']:
        return jsonify({'error': 'Cannot alter a closed transaction.'}), 400
        
    order.status = chef_status
    db.session.commit()

    return jsonify({'message': f'Order {order_id} status stepped to {chef_status}.'}), 200