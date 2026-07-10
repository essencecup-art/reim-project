import os, html
import stripe
from flask import Blueprint, redirect, url_for, request, jsonify, session
from core.models import Order, MenuItem
from core.extensions import db
import logging

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "your_stripe_test_secret_key")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_temporary_dev_key")

payment_bp = Blueprint('payment', __name__)

def alert_staff_kitchen_terminal(order_id):
    """
    Registers a new active order alert for the kitchen staff system.
    This prepares the database record to be pulled by the Staff Dashboard.
    """
    try:
        # 1. Log the alert inside the server terminal for debugging
        logging.info(f"🚨 ALERT: New Cash Order #{order_id} sent to the kitchen terminal queue.")
        
        # 2. (Optional future-proofing) If you use Flask-SocketIO later, you would add:
        # socketio.emit('new_order_alert', {'order_id': order_id}, room='kitchen_staff')
        
        return True
    except Exception as e:
        print(f"Failed to trigger kitchen notification: {str(e)}")
        return False
    
def get_active_cart_total_cents():
    """
    Looks up the active cart items stored inside the Flask session,
    calculates the total cost, and converts it to cents for Stripe.
    """
    cart = session.get('cart', {}) # Expects a dict structure like { 'item_id': quantity }
    total_cents = 0
    
    if not cart:
        return 0
        
    for item_id, quantity in cart.items():
        item = MenuItem.query.get(int(item_id))
        if item:
            # Assuming item.price is stored as a float/decimal (e.g., 12.50)
            total_cents += int(item.price) * quantity
            
    return total_cents

def get_cart_items_description_string():
    """
    Generates a human-readable string of the items in the cart for order description.
    Example: "2x Cheeseburger, 1x Fries, 3x Soda"
    """
    cart = session.get('cart', {})
    item_descriptions = []
    
    for item_id, quantity in cart.items():
        item = MenuItem.query.get(int(item_id))
        if item:
            item_descriptions.append(f"{quantity}x {item.name}")
    
    return ', '.join(item_descriptions) if item_descriptions else "No items"

@payment_bp.route('/handle-settlement', methods=['POST'])
def handle_settlement():
    fulfillment_method = request.form.get('fulfillment_method')
    payment_method = request.form.get('payment_method')
    
    table_number = html.escape(request.form.get('table_number', '')).strip()[:10] 
    delivery_address = html.escape(request.form.get('delivery_address', '')).strip()[:500] 
    
    # 📍 Capture the GPS coordinates sent by your checkout layout map
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    
    current_total = get_active_cart_total_cents() 
    base_description = get_cart_items_description_string() 
    
    if fulfillment_method == 'Delivery' and delivery_address:
        final_description = f"📍 DELIVERY TO: {delivery_address} | Items: {base_description}"
    elif fulfillment_method == 'Dine-In' and table_number:
        final_description = f"🍽️ DINE-IN (Table {table_number}) | Items: {base_description}"
    else:
        final_description = f"🛍️ TAKEAWAY | Items: {base_description}"

    new_order = Order(
        total_amount=current_total,
        payment_method=payment_method,
        table_number=table_number if fulfillment_method == 'Dine-In' else None,
        description=final_description,
        status='Pending'
    )
    
    db.session.add(new_order)
    db.session.commit()

    if payment_method == 'Stripe':
        return redirect(url_for('payment.create_checkout_session', order_id=new_order.id))
    else: 
        new_order.status = 'Pending Cash Payment'
        db.session.commit()
        alert_staff_kitchen_terminal(new_order.id)
        return redirect(url_for('cart.order_success', order_id=new_order.id))


@payment_bp.route('/create-checkout-session/<int:order_id>', methods=['GET','POST'])
def create_checkout_session(order_id):
    order = Order.query.get_or_404(order_id)
    
    # 🔒 Shield against the infinite 7% loop by calculating purely in memory
    happiness_fee = int(order.total_amount * 0.07)
    
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': f"LuxeEats Premium Order #{order.id}",
                        },
                        'unit_amount': order.total_amount, 
                    },
                    'quantity': 1,
                },
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': "✨ Happiness Fee (7%)",
                        },
                        'unit_amount': happiness_fee, 
                    },
                    'quantity': 1,
                }
            ],
            mode='payment',
            metadata={
                'order_id': str(order.id),
                'happiness_fee_added': str(happiness_fee)
            },
            success_url=url_for('payment.payment_success', order_id=order.id, _external=True),
            cancel_url=url_for('payment.payment_cancel', order_id=order.id, _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return f"Marketplace payment session configuration broken: {str(e)}", 500


@payment_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('HTTP_STRIPE_SIGNATURE') or request.headers.get('Stripe-Signature')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify({'error': 'Invalid signature'}), 400

    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        order_id = session_obj.get('metadata', {}).get('order_id')
        fee_to_add = int(session_obj.get('metadata', {}).get('happiness_fee_added', 0))
        
        if order_id:
            order = Order.query.get(int(order_id))
            if order:
                # Commit the 7% fee total and flag as Paid simultaneously
                order.total_amount += fee_to_add
                order.status = 'Paid'
                db.session.commit()
                print(f"✅ Webhook Verified: Order #{order_id} updated with fee and marked as Paid.")

    return jsonify({'success': True}), 200


@payment_bp.route('/payment-success/<int:order_id>')
def payment_success(order_id):
    return redirect(url_for('cart.order_success', order_id=order_id))


@payment_bp.route('/payment-cancel/<int:order_id>')
def payment_cancel(order_id):
    return redirect(url_for('cart.show_cart'))


