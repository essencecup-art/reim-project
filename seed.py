from core import create_app
from core.extensions import db
from core.models import MenuItem

app = create_app()

with app.app_context():
    db.create_all()

    if MenuItem.query.first():
        print("⚡ Database already has food items. Skipping seed!")
    else:
        print("🍳 Seeding premium items into the LuxeEats database...")
        
        dummy_menu = [
            MenuItem(
                name="Trilogy Truffle Burger", 
                price=2400, 
                category="Burgers",
                description="Dry-aged wagyu blend, shaved black winter truffle, triple-cream brie, on a toasted artisan brioche.",
                image_url=None
            ),
            MenuItem(
                name="A5 Miyazakigyu Ribeye", 
                price=11500, 
                category="Steaks",
                description="8oz pristine Japanese A5 Wagyu steak, hand-carved, served with smoked sea salt crystals.",
                image_url=None
            ),
            MenuItem(
                name="Crispy Gold-Leaf Tacos", 
                price=1800, 
                category="Tacos",
                description="Slow-braised pork belly, pickled habanero onions, micro cilantro, served in hand-pressed heirloom corn tortillas.",
                image_url=None
            ),
            MenuItem(
                name="Glacier Ice Orchid Elixir", 
                price=1200, 
                category="Beverages",
                description="Crafted botanical mocktail infused with white tea, cold-pressed lychee, and edible flower garnishes.",
                image_url=None
            ),
            MenuItem(
                name="Luxe Lava Fondant", 
                price=1400, 
                category="Desserts",
                description="Dark Belgian chocolate cake with a molten center, accompanied by Madagascar vanilla bean gelato.",
                image_url=None
            )
        ]
        
        db.session.add_all(dummy_menu)
        db.session.commit()
        print("🚀 LuxeEats database successfully seeded, gang!")