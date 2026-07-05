import os
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from requests_oauthlib import OAuth2Session
from core.extensions import db
from core.models import User

auth_bp = Blueprint('auth', __name__)

# 🔑 Paste your Google Developer Keys here
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://127.0.0.1:5000/auth/callback"

# Google OAuth endpoints
AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USER_INFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# This line allows local HTTP development (Google normally forces HTTPS only)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

@auth_bp.route('/login')
def login():
    google_id = os.getenv("GOOGLE_CLIENT_ID")
    return render_template('login.html',client_id=google_id)

@auth_bp.route('/auth/callback')
def callback():
    """Step B: Google catches them, validates them, and sends them back here"""
    google = OAuth2Session(GOOGLE_CLIENT_ID, state=session.get('oauth_state'), redirect_uri=REDIRECT_URI)
    
    try:
        # Swap the single-use code from Google for a secure access token
        google.fetch_token(
            TOKEN_URL,
            client_secret=GOOGLE_CLIENT_SECRET,
            authorization_response=request.url
        )
        
        # Use that fresh access token to look up who this profile belongs to
        user_info = google.get(USER_INFO_URL).json()
        user_email = user_info.get('email')
        user_name = user_info.get('name')
        
        # 👑 THE ADMIN CHECK: Look up if this email exists as an Admin in our DB
        matched_user = User.query.filter_by(email=user_email).first()
        
        is_admin_flag = False
        if matched_user and matched_user.is_admin:
            is_admin_flag = True
        
        # Save user variables securely inside the encrypted Flask session cookie
        session['user'] = {
            'email': user_email,
            'name': user_name,
            'picture': user_info.get('picture'),
            'is_admin': is_admin_flag # Linked straight out of your database condition!
        }
        
        if is_admin_flag:
            flash(f"Welcome back, Captain {user_name}!", "success")
            # You can change 'main.menu' to whatever your kitchen/admin dashboard route is called later
            return redirect(url_for('main.menu')) 
        else:
            flash(f"Logged in as {user_name}.", "success")
            return redirect(url_for('main.menu'))
            
    except Exception as e:
        flash("Google authentication ran into an error.", "error")
        return redirect(url_for('main.menu'))


@auth_bp.route('/logout')
def logout():
    """Step C: Clear the user details out of session storage"""
    session.pop('user', None)
    flash("Logged out successfully.", "info")
    return redirect(url_for('main.menu'))