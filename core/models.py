from core.extensions import db
from datetime import datetime

class MenuItem(db.Model):
    """Stores the food and drinks available for order"""
    __tablename__ = 'menu_items'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)  # Stored in cents for Stripe (e.g., $10.50 = 1050)
    category = db.Column(db.String(50), nullable=False)  # Appetizer, Main, Drink
    image_url = db.Column(db.String(255), nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    description = db.Column(db.String(255), nullable=True)

class Order(db.Model):
    """Stores the final checkout orders (Cash or Card via Stripe)"""
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index = True)  # Hooked to Google Login ID or session
    total_amount = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # 'stripe' or 'cash'
    status = db.Column(db.String(20), default='Pending', index=True)  # Pending, Paid, Completed
    created_at = db.Column(db.DateTime, default=datetime.now, index = True)
    description = db.Column(db.Text, nullable=True)
    table_number = db.Column(db.String(10), nullable=True)  # Optional for dine-in orders
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    user = db.relationship('User', backref=db.backref('orders', lazy= 'joined'))
    
    # Establish a relationship link to the individual items inside this order
    items = db.relationship('OrderItem', backref=db.backref('order', lazy="joined"))

class OrderItem(db.Model):
    """The individual breakdown rows inside a single Order receipt"""
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_items.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

# Inside core/models.py

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False) # Google emails are unique
    name = db.Column(db.String(100), nullable=True)
    is_admin = db.Column(db.Boolean, default=False) # 🌟 Your is_admin flag! Default is False.
    is_staff = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<User {self.email} - Admin: {self.is_admin}>"