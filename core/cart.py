from flask import Blueprint, session, jsonify, request, render_template, redirect, url_for, flash
from core.models import MenuItem, Order, OrderItem, User
from core.extensions import db

cart_bp = Blueprint('cart', __name__)

def get_total(cart):
    total = 0
    for item_id, quantity in cart.items():
        item = MenuItem.query.get(int(item_id))
        if item:
            total += item.price * quantity
    return total

@cart_bp.route('/cart/add/<int:item_id>', methods=['POST'])
def add_item(item_id):
    cart = session.get('cart', {})
    item_id_str = str(item_id)
    
    cart[item_id_str] = cart.get(item_id_str, 0) + 1
    session['cart'] = cart
    session.modified = True
    
    item = MenuItem.query.get(item_id)
    subtotal = item.price * cart[item_id_str] if item else 0
    
    return jsonify({
        "success": True,
        "quantity": cart[item_id_str],
        # 🌟 FIXED: Clean Python string formatting instead of Jinja pipes
        "subtotal": "{:.2f}".format(subtotal / 100),
        "grand_total": "{:.2f}".format(get_total(cart) / 100),
        "removed": False,
        "cart_empty": len(cart) == 0
    })

@cart_bp.route('/cart/decrease/<int:item_id>', methods=['POST'])
def decrease_item(item_id):
    cart = session.get('cart', {})
    item_id_str = str(item_id)
    
    removed = False
    quantity = 0
    subtotal = 0
    
    if item_id_str in cart:
        if cart[item_id_str] > 1:
            cart[item_id_str] -= 1
            quantity = cart[item_id_str]
            item = MenuItem.query.get(item_id)
            subtotal = item.price * quantity if item else 0
        else:
            del cart[item_id_str]
            removed = True
            
    session['cart'] = cart
    session.modified = True
    
    return jsonify({
        "success": True,
        "quantity": quantity,
        # 🌟 FIXED: Clean Python string formatting instead of Jinja pipes
        "subtotal": "{:.2f}".format(subtotal / 100),
        "grand_total": "{:.2f}".format(get_total(cart) / 100),
        "removed": removed,
        "cart_empty": len(cart) == 0
    })

@cart_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
def remove_item(item_id):
    cart = session.get('cart', {})
    item_id_str = str(item_id)
    
    if item_id_str in cart:
        del cart[item_id_str]
        
    session['cart'] = cart
    session.modified = True
    
    return jsonify({
        "success": True,
        "quantity": 0,
        "subtotal": "0.00",
        # 🌟 FIXED: Clean Python string formatting instead of Jinja pipes
        "grand_total": "{:.2f}".format(get_total(cart) / 100),
        "removed": True,
        "cart_empty": len(cart) == 0
    })

@cart_bp.route('/cart')
def show_cart():
    cart = session.get('cart', {})
    cart_items_detailed = []
    for item_id, quantity in cart.items():
        item = MenuItem.query.get(int(item_id))
        if item:
            cart_items_detailed.append({
                'model': item,
                'quantity': quantity,
                'subtotal': item.price * quantity
            })
    return render_template('cart.html', cart_items=cart_items_detailed, total=get_total(cart))

@cart_bp.route('/checkout')
def checkout():
    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('main.menu'))
        
    total_price = get_total(cart)
    return render_template('checkout.html', total=total_price)



@cart_bp.route('/checkout/submit', methods=['POST'])
def submit_order():
    # 1. Grab the current cart from the user's session memory
    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty!", "error")
        return redirect(url_for('cart.show_cart')) # ◄── FIXED: Changed from view_cart to show_cart
        
    # 2. Extract the form details filled out by the user
    table_number = request.form.get('table_number')
    payment_method = request.form.get('payment_method', 'Cash') # Default to Cash
    
    # 3. Build a clean, single-string order summary text for the kitchen staff
    summary_items = []
    total_amount = 0
    
    # ◄── FIXED: Corrected loop to handle the flat cart structure {"item_id": quantity}
    for item_id, quantity in cart.items():
        item = MenuItem.query.get(int(item_id))
        if item:
            summary_items.append(f"{quantity}x {item.name}")
            total_amount += item.price * quantity
        
    order_description = ", ".join(summary_items)

    user_email = session['user'].get('email')
    user = User.query.filter_by(email=user_email).first() if user_email else None
    current_user_id = user.id if user else None
    
    # 4. Instantiate our new Order database record
    new_order = Order(
        user_id=current_user_id,
        table_number=table_number,
        description=order_description,
        total_amount=total_amount,
        payment_method=payment_method,
        status='Pending', # Every order starts as Pending!
    ).with_for_update()  # ◄── FIXED: Added to prevent race conditions during database writes
    
    try:
        # 5. Lock it into the database file
        db.session.add(new_order)
        db.session.commit()
        
        # 6. Clear out the user's cart session so their tray is empty for next time
        session['cart'] = {}
        
        # ◄── FIXED: BRIDGE TO STRIPE CHECKOUT SESSIONS AUTOMATICALLY ──►
        if payment_method == 'Stripe':
            return redirect(url_for('payment.create_checkout_session', order_id=new_order.id))
        
        flash("Order placed successfully!", "success")
        return redirect(url_for('cart.order_success', order_id=new_order.id))
        
    except Exception as e:
        db.session.rollback()
        print(f"Database insertion error: {e}")
        flash("Something went wrong processing your order.", "error")
        return redirect(url_for('cart.show_cart'))

@cart_bp.route('/checkout/success/<int:order_id>')
def order_success(order_id):
    # 1. Fetch the exact order from the database
    order = Order.query.get_or_404(order_id)
    
    # 2. Handshake: Pass all three variables directly into the template
    return render_template(
        'order_success.html', 
        order_id=order.id, 
        method=order.payment_method, 
        total=order.total_amount
    )