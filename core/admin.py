from flask import Blueprint, render_template, jsonify,flash, redirect, url_for, session, request
from core.models import Order, User
from core.extensions import db
from functools import wraps

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f) # 👈 The magic line!
    def decorated_function(*args, **kwargs):
        # 1. Look inside the encrypted session cookie
        user = session.get('user')
        
        # 2. If no user is logged in, or they aren't an admin -> BOOT THEM
        if not user or not user.get('is_admin'):
            flash("Unauthorized access. Management clearance required.", "error")
            return redirect(url_for('main.home')) # Kick them back to your beautiful welcome page
            
        # 3. If they pass the check, let them proceed to the route function
        return f(*args, **kwargs)
        
    return decorated_function

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    # 1. Pull ALL orders from the database to compute business metrics
    all_orders = Order.query.order_by(Order.updated_at.desc()).all()
    
    # 2. THE HANDSHAKE: Filter only active kitchen tickets for the chef grid
    # This uses the exact logic function you built yesterday!
    active_kitchen_tickets = get_active_kitchen_tickets(all_orders)
    
    # 3. Calculate gross revenue from completed or paid orders
    # (Filters out cancelled orders so metrics stay completely accurate)
    gross_revenue = sum(order.total_amount for order in all_orders if order.status != 'Cancelled')
    
    # 4. Count how many active tickets are currently outstanding
    active_count = len(active_kitchen_tickets)
    
    # 5. Send everything right to your HTML context variables
    return render_template(
        'admin_dashboard.html', 
        orders=active_kitchen_tickets, # Only active ones hit the card grid now!
        revenue=gross_revenue,
        pending=active_count,
        total_orders_count=len(all_orders)
    )

@admin_bp.route('/api/orders/stream')
@admin_required
def orders_stream():
    """An API route that returns raw data for our JS live-reloader to read."""
    orders = Order.query.order_by(Order.status.desc(), Order.created_at.desc()).all()
    
    # Format the data into a clean dictionary list that JS understands
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
        'pending': sum(1 for o in orders if o.status == 'Pending')
    })

@admin_bp.route('/api/orders/<int:order_id>/update', methods=['POST'])
@admin_required
def update_order_status(order_id):
    """An API route that allows admins to update the status of an order."""
    data = request.json
    if not data or 'chef_status' not in data:
        return jsonify({'error': 'Invalid request. Missing chef status.'}), 400
    chef_status = data.get('chef_status')

    order = Order.query.with_for_update().get(order_id)  # Lock the row for this transaction
    if not order:
        return jsonify({'error': 'Order not found.'}), 404
    
    if order.status == 'Cancelled' or order.status == 'Paid':
        return jsonify({'error': 'Cannot update a completed order.'}), 400
    # Update the order status based on the chef_status received
    order.status = chef_status
    db.session.commit()

    return jsonify({'message': f'Order {order_id} status updated to {chef_status}.'}), 200

def get_active_kitchen_tickets(all_orders):
    """Helper function to filter and return only active kitchen tickets."""
    active_tickets = []
    for order in all_orders:
        if order.status not in ['Cancelled', 'Paid']:
            active_tickets.append(order)
    return active_tickets



