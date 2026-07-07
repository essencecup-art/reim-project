import os
from flask import Flask
from core.extensions import db, migrate

def create_app():
    # 1. Dynamically find the absolute path of the directory containing this file (the core folder)
    core_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 2. Join it with the templates folder sitting one level up
    template_dir = os.path.abspath(os.path.join(core_dir, '..', 'templates'))
    print(f"\n🔍 DEBUG: Flask is looking for templates here: {template_dir}\n")
    # 3. Feed the exact, unshakeable absolute path directly to Flask
    
    root_dir = os.path.abspath(os.path.join(core_dir, '..'))
    db_path = os.path.join(root_dir, 'dining.db')

    app = Flask(__name__, template_folder=template_dir)
    
    # --- Rest of your config remains exactly the same ---
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', f'sqlite:///{db_path}')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'temporary-dev-key-12345'
    
    from core.models import MenuItem, Order, OrderItem, User

    db.init_app(app)
    migrate.init_app(app, db)
    
    # with app.app_context():
    #     db.create_all()
    from core.cart import cart_bp   
    from core.main import main_bp
    from core.admin import admin_bp, staff_bp
    from core.auth import auth_bp
    from core.payment import payment_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(payment_bp)
    return app