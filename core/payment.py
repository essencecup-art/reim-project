import os
import stripe
from flask import Blueprint, redirect, url_for, request, jsonify
from core.models import Order
from core.extensions import db

# Loaded safely via your Option 3 environment variables
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "your_stripe_test_secret_key")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_temporary_dev_key")

payment_bp = Blueprint('payment', __name__)

@payment_bp.route('/create-checkout-session/<int:order_id>', methods=['GET','POST'])
def create_checkout_session(order_id):
    order = Order.query.get_or_404(order_id)
    luxeeats_fee = int(order.total_amount * 0.10) 
    
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"LuxeEats Premium Order #{order.id}",
                    },
                    'unit_amount': order.total_amount,
                },
                'quantity': 1,
            }],
            mode='payment',
            payment_intent_data={
                'application_fee_amount': luxeeats_fee,
                'transfer_data': {
                    'destination': 'acct_12345XYZ', # Replace with real connected restaurant ID
                },
            },
            # 🔒 SENIOR MOVE: Pass the order ID securely in metadata so the webhook can read it
            metadata={
                'order_id': str(order.id)
            },
            success_url=url_for('payment.payment_success', order_id=order.id, _external=True),
            cancel_url=url_for('payment.payment_cancel', order_id=order.id, _external=True),
        )
        
        return redirect(checkout_session.url, code=303)
        
    except Exception as e:
        return f"Marketplace payment failed: {str(e)}", 500


@payment_bp.route('/payment-success/<int:order_id>')
def payment_success(order_id):
    """
    🔒 SECURITY UPDATE:
    This route now ONLY routes the user visually to the success page.
    It NO LONGER updates the database status. The webhook handles that.
    """
    return redirect(url_for('cart.order_success', order_id=order_id))


@payment_bp.route('/payment-cancel/<int:order_id>')
def payment_cancel(order_id):
    return redirect(url_for('cart.show_cart'))


@payment_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    🔒 THE VERIFIED HANDSHAKE:
    Stripe hits this endpoint directly server-to-server when a charge clears.
    """
    payload = request.data
    sig_header = request.headers.get('HTTP_STRIPE_SIGNATURE') or request.headers.get('Stripe-Signature')
    event = None

    try:
        # Verify that the request actually came from Stripe using our signing secret
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid cryptographic signature (someone trying to spoof Stripe)
        return jsonify({'error': 'Invalid signature'}), 400

    # If the signature is valid, process the payment payload safely
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        
        # Extract that secure metadata order_id we tucked away earlier
        order_id = session_obj.get('metadata', {}).get('order_id')
        
        if order_id:
            # Safely perform the database state mutation out of reach of the user
            order = Order.query.get(int(order_id))
            if order:
                order.status = 'Paid'
                db.session.commit()
                print(f" Webhook Verified: Order #{order_id} has been marked as PAID.")

    return jsonify({'success': True}), 200