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