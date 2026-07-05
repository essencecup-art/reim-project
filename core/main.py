from flask import Blueprint, render_template, session, redirect, url_for

from core.extensions import db
from core.models import MenuItem

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    # Redirecting the home page layout to display the menu layout for now
    return render_template('welcome.html')

@main_bp.route('/menu')
def menu():
    items = MenuItem.query.filter_by(is_available=True).all()

    return render_template('menu.html',menu_items= items)

















# @main_bp.route('/seed-database')
# def seed_database():
#     """Temporary route to populate the database with luxury items"""
#     # Check if we already have items so we don't duplicate them
#     if MenuItem.query.first() is None:
#         item1 = MenuItem(
#             name="Truffle Wagyu Burger",
#             price=2400,  # $24.00 stored in cents
#             category="Main",
#             description="Aged wagyu, shaved black truffle, brioche bun.",
#             is_available=True
#         )
#         item2 = MenuItem(
#             name="Caviar Frites",
#             price=1800,  # $18.00 stored in cents
#             category="Appetizer",
#             description="Crisp golden fries topped with premium Ossetra caviar and chive creme fraiche.",
#             is_available=True
#         )
#         item3 = MenuItem(
#             name="Saffron Rose Lemonade",
#             price=850,   # $8.50 stored in cents
#             category="Drink",
#             description="Infused organic lemon juice with Persian saffron and wild rose water.",
#             is_available=True
#         )

#         # Stage them in memory, then slam commit them into dining.db
#         db.session.add_all([item1, item2, item3])
#         db.session.commit()
#         return "Database seeded successfully with luxury items!"
    
#     return "Database already has items. No seeding needed."