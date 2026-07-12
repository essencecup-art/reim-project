from datetime import datetime
from flask import Blueprint, render_template, jsonify, flash, redirect, url_for, session, request
from core.models import Order, User
from core.extensions import db
from functools import wraps
from sqlalchemy import func, extract
from sqlalchemy.orm import selectinload


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
    all_orders = Order.query.options(selectinload(Order.items)).order_by(Order.created_at.desc()).all()
    
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    gross_revenue = db.session.query(func.sum(Order.total_amount)).filter(Order.status != 'Cancelled').scalar() or 0
    
    monthly_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status != 'Cancelled',
        extract('year',Order.created_at) == current_year,
        extract('month',Order.created_at.month) == current_month
    ).scalar() or 0

    pending_count = db.session.query(func.count(Order.id)).filter(
        ~Order.status.in_(['Cancelled', 'Completed'])
    ).scalar() or 0

    return render_template(
        'admin_dashboard.html', 
        orders=all_orders,
        revenue=gross_revenue,
        monthly_revenue=monthly_revenue,
        pending=pending_count,
        total_orders_count=len(all_orders)
    )


@admin_bp.route('/api/orders/stream')
@admin_required
def orders_stream():
    """API endpoint providing the live background polling data stream for admins."""
    orders = Order.query.options(selectinload(Order.items)).order_by(Order.created_at.desc()).all()
    
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    orders_data = []
    for o in orders:
        orders_data.append({
            'id': o.id,
            'table': o.table_number if o.table_number else "00",
            'description': o.description,
            'status': o.status,
            'payment_method': o.payment_method,
            'amount': f"${o.total_amount / 100:.2f}",
            'time': o.created_at.strftime('%H:%M') if o.created_at else "00:00"
        })
        
    # Calculate live counters so frontend JavaScript can dynamically re-render metrics cards
    gross_revenue_calc = db.session.query(func.sum(Order.total_amount)).filter(Order.status != 'Cancelled').scalar() or 0
    monthly_revenue_calc = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status != 'Cancelled',
        extract('year',Order.created_at) == current_year,
        extract('month',Order.created_at) == current_month
    ).scalar() or 0
    
    pending_calc = db.session.query(func.count(Order.id)).filter(
        ~Order.status.in_(['Cancelled', 'Completed'])
    ).scalar() or 0

    return jsonify({
        'orders': orders_data,
        'revenue': f"${gross_revenue_calc:.2f}",
        'monthly_revenue': f"${monthly_revenue_calc:.2f}",
        'pending': pending_calc,
        'total_orders_count': len(orders)
    })

@admin_bp.route('/api/orders/<int:order_id>/update', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    """Dedicated admin pathway to shift order states directly from the command center."""
    data = request.json
    if not data or 'chef_status' not in data:
        return jsonify({'error': 'Invalid payload data.'}), 400
    chef_status = data.get('chef_status')

    order = Order.query.filter_by(id=order_id).with_for_update().first()
    if not order:
        return jsonify({'error': 'Order resource not found.'}), 404
        
    # 🌟 GUARD: Protect finalized transactions from layout mismatch states
    if order.status in ['Cancelled', 'Completed'] and chef_status not in ['Cancelled', 'Completed']:
        return jsonify({'error': 'Cannot alter a finalized, closed transaction.'}), 400
        
    order.status = chef_status
    db.session.commit()

    return jsonify({'message': f'Admin updated order {order_id} to {chef_status}.'}), 200

# =====================================================================
# 👨‍🍳 KITCHEN LINE ENVIRONMENT (staff_bp)
# =====================================================================

@staff_bp.route('/kitchen')
@staff_required
def kitchen_feed():
    """Operational ticket monitor view with dynamic tab filtering (?view=all/active/reserved)."""
    # 1. Catch which mode the chef clicked from the URL query parameters (default to 'all')
    view_mode = request.args.get('view', 'all')
    
    # Base query to fetch orders with their items loaded efficiently
    query = Order.query.options(selectinload(Order.items))
    
    # 2. Filter the database query based on the active tab mode
    if view_mode == 'active':
        # Shows tickets currently on the line cooking
        orders = query.filter(
            Order.status.in_(['Paid', 'Preparing', 'Pending Cash Payment', 'active'])
        ).order_by(Order.created_at.asc()).all()
        
    elif view_mode == 'reserved':
        # Shows ONLY upcoming reservations, sorted chronologically (earliest first!)
        orders = query.filter(
            Order.status == 'reserved'
        ).order_by(Order.created_at.asc()).all()
        
    else:  # view_mode == 'all'
        # Shows everything the kitchen needs to care about
        orders = query.filter(
            Order.status.in_(['Paid', 'Preparing', 'Pending Cash Payment', 'active', 'reserved'])
        ).order_by(Order.created_at.asc()).all()

    
    # Pass the filtered orders AND the current view mode back to the HTML template
    return render_template('kitchen_feed.html', orders=orders, current_view=view_mode)


@staff_bp.route('/api/orders/stream')
@staff_required
def kitchen_stream():
    """Live background polling stream that respects the selected kitchen tab filter."""
    view_mode = request.args.get('view', 'all')
    query = Order.query.options(selectinload(Order.items))
    
    # Mirror the exact same database filters so the live updates don't break the user's view
    if view_mode == 'active':
        tickets = query.filter(Order.status.in_(['Paid', 'Preparing', 'Pending Cash Payment', 'active'])).order_by(Order.created_at.asc()).all()
    elif view_mode == 'reserved':
        tickets = query.filter(Order.status == 'reserved').order_by(Order.created_at.asc()).all()
    else:
        tickets = query.filter(Order.status.in_(['Paid', 'Preparing', 'Pending Cash Payment', 'active', 'reserved'])).order_by(Order.created_at.asc()).all()
    
    tickets_data = []
    for t in tickets:
        tickets_data.append({
            'id': t.id,
            'table': t.table_number if t.table_number else "00",
            'description': t.description,
            'status': t.status,
            'time': t.created_at.strftime('%H:%M') if t.created_at else "00:00"
        })
        
    return jsonify({'orders': tickets_data})


# =====================================================================
# 📡 CLEANED SHARED API PIPELINE
# =====================================================================

@staff_bp.route('/api/orders/<int:order_id>/update', methods=['POST'])
@staff_required
def update_order_status(order_id):
    """Allows staff or admin to shift an order state dynamically on the line."""
    data = request.json
    if not data or 'chef_status' not in data:
        return jsonify({'error': 'Invalid payload data.'}), 400
    chef_status = data.get('chef_status')

    order = Order.query.filter_by(id=order_id).with_for_update().first()
    if not order:
        return jsonify({'error': 'Order resource not found.'}), 404
    
    # Allows 'Paid' or 'Preparing' orders to safely transition to 'Preparing' and 'Completed'
    if order.status in ['Cancelled', 'Completed'] and chef_status not in ['Cancelled', 'Completed']:
        return jsonify({'error': 'Cannot alter a finalized, closed transaction.'}), 400
        
    order.status = chef_status
    db.session.commit()

    return jsonify({'message': f'Order {order_id} status stepped to {chef_status}.'}), 200