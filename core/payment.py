import os, html
import requests
import stripe
from flask import Blueprint, redirect, url_for, request, jsonify, session
from core.models import Order, MenuItem
from core.extensions import db
import logging

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "your_stripe_test_secret_key")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_temporary_dev_key")
UBER_CLIENT_ID = os.getenv("UBER_CLIENT_ID", "your_uber_client_id")
UBER_CLIENT_SECRET = os.getenv("UBER_CLIENT_SECRET", "your_uber_client_secret")
payment_bp = Blueprint('payment', __name__)

def alert_staff_kitchen_terminal(order_id):
    """
    Registers a new active order alert for the kitchen staff system.
    """
    try:
        logging.info(f"🚨 ALERT: New Cash Order #{order_id} sent to the kitchen terminal queue.")
        return True
    except Exception as e:
        print(f"Failed to trigger kitchen notification: {str(e)}")
        return False
    
def get_active_cart_total_cents():
    """
    Looks up the active cart items, calculates total, converts to cents.
    """
    cart = session.get('cart', {})
    total_cents = 0
    
    if not cart:
        return 0
        
    for item_id, quantity in cart.items():
        item = MenuItem.query.get(int(item_id))
        if item:
            total_cents += int(item.price) * quantity
            
    return total_cents

def get_cart_items_description_string():
    """
    Generates a human-readable string of items for order description.
    """
    cart = session.get('cart', {})
    item_descriptions = []
    
    for item_id, quantity in cart.items():
        item = MenuItem.query.get(int(item_id))
        if item:
            item_descriptions.append(f"{quantity}x {item.name}")
    
    return ', '.join(item_descriptions) if item_descriptions else "No items"

def get_uber_access_token():
    # Use the explicit Sandbox Auth URL
    auth_url = "https://login.uber.com/oauth/v2/token" # <--- IMPORTANT: Note the 'sandbox-' prefix
    payload = {
        "client_id": UBER_CLIENT_ID,
        "client_secret": UBER_CLIENT_SECRET,
        "grant_type": "client_credentials",
        "scope": "eats.deliveries" 
    }
    try:
        response = requests.post(auth_url, data=payload)
        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            # We now know this is where it's failing
            logging.error(f"Uber Auth Failed: {response.text}")
            return None
    except Exception as e:
        logging.error(f"Auth request crashed: {str(e)}")
        return None

def get_delivery_quote_cents(lat, lng):
    token = get_uber_access_token()
    
    # FIX: If token fails, just return a fallback fee and print the error.
    # Do not try to return 'response' because it doesn't exist here.
    if not token:
        print("DEBUG: Uber Auth Failed - Using fallback fee")
        return 1250 

    api_url = "https://sandbox.api.uber.com/v1/deliveries/quotes" 
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    payload = {
        "pickup_address": os.getenv("UBER_PICKUP_ADDRESS", "123 Main St, San Francisco, CA 94105"), 
        "dropoff_location": {"lat": lat, "lng": lng}
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=5)
        
        # UNMASKING THE ERROR:
        if response.status_code != 200:
            print(f"🚨 UBER ERROR CODE: {response.status_code}")
            print(f"🚨 UBER ERROR RESPONSE: {response.text}")
            return 88888 
            
        data = response.json()
        return int(round(float(data.get('fee', 5.00)) * 100))
        
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return 77777

@payment_bp.route('/get-delivery-fee', methods=['POST'])
def get_delivery_fee():
    data = request.json
    lat = data.get('latitude')
    lng = data.get('longitude')
    cents = get_delivery_quote_cents(lat, lng) 
    return jsonify({'fee_cents': cents, 'fee_dollars': cents / 100})

@payment_bp.route('/handle-settlement', methods=['POST'])
def handle_settlement():
    print(f"DEBUG FORM DATA: {request.form}")
    fulfillment_method = request.form.get('fulfillment_method')
    payment_method = request.form.get('payment_method')
    
    table_number = html.escape(request.form.get('table_number', '')).strip()[:10] 
    delivery_address = html.escape(request.form.get('delivery_address', '')).strip()[:500] 
    
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    
    current_total = get_active_cart_total_cents() 
    base_description = get_cart_items_description_string() 
    
    if fulfillment_method == 'Delivery' and delivery_address:
        delivery_cost = get_delivery_quote_cents(float(latitude), float(longitude))     
        current_total += delivery_cost
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
    
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            payment_intent_data={'capture_method': 'manual'},
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': f"LuxeEats Order #{order.id}",
                        },
                        'unit_amount': order.total_amount, 
                    },
                    'quantity': 1,
                }
            ],
            mode='payment',
            metadata={'order_id': str(order.id)},
            success_url=url_for('payment.payment_success', order_id=order.id, _external=True),
            cancel_url=url_for('payment.payment_cancel', order_id=order.id, _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return f"Payment session configuration broken: {str(e)}", 500

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
        
        if order_id:
            order = Order.query.get(int(order_id))
            if order:
                order.status = 'Paid'
                db.session.commit()
                print(f"✅ Webhook Verified: Order #{order_id} marked as Paid.")

    return jsonify({'success': True}), 200

@payment_bp.route('/payment-success/<int:order_id>')
def payment_success(order_id):
    return redirect(url_for('cart.order_success', order_id=order_id))

@payment_bp.route('/payment-cancel/<int:order_id>')
def payment_cancel(order_id):
    return redirect(url_for('cart.show_cart'))