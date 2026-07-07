import os
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from requests_oauthlib import OAuth2Session
from core.extensions import db
from core.models import User

auth_bp = Blueprint('auth', __name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# 🌐 DYNAMIC REDIRECT URL: Automatically switches between Render and Localhost
if os.getenv("DATABASE_URL") or os.getenv("FLASK_ENV") == "production":
    REDIRECT_URI = "https://reim-project.onrender.com/auth/callback"
    # Turn off insecure transport in production
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '0'
else:
    REDIRECT_URI = "http://127.0.0.1:5000/auth/callback"
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Google OAuth endpoints
AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USER_INFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@auth_bp.route('/login')
def login():
    """Step A: Generate the official Google Authorization URL and redirect them"""
    # We ask for profile and email scopes
    scopes = ["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email"]
    
    google = OAuth2Session(GOOGLE_CLIENT_ID, redirect_uri=REDIRECT_URI, scope=scopes)
    
    # authorization_url is the official Google login link
    # state prevents Cross-Site Request Forgery (CSRF)
    authorization_url, state = google.authorization_url(AUTH_BASE_URL)
    
    # Save state to session so we can verify it when they come back
    session['oauth_state'] = state
    
    # Send the user straight to Google's official login page!
    return redirect(authorization_url)


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
        
        # 💡 BONUS FIX: If they don't exist in the DB yet, create them!
        if not matched_user:
            matched_user = User(
                username=user_name,
                email=user_email,
                is_admin=False # Default to normal user
            )
            db.session.add(matched_user)
            db.session.commit()
        
        if user_email == 'essencecup@gmail.com' and not matched_user.is_admin:
            matched_user.is_admin = True
            db.session.commit() # This saves it permanently to your live DB!
            
        is_admin_flag = matched_user.is_admin
        
        # Save user variables securely inside the encrypted Flask session cookie
        session['user'] = {
            'email': user_email,
            'name': user_name,
            'picture': user_info.get('picture'),
            'is_admin': is_admin_flag 
        }
        
        if is_admin_flag:
            flash(f"Welcome back, Captain {user_name}!", "success")
            return redirect(url_for('admin.dashboard')) 
        else:
            flash(f"Logged in as {user_name}.", "success")
            return redirect(url_for('main.menu'))
            
    except Exception as e:
        print(f"OAuth Error details: {e}") # This helps you debug in Render logs if it breaks
        flash("Google authentication ran into an error.", "error")
        return redirect(url_for('main.menu'))


@auth_bp.route('/logout')
def logout():
    """Step C: Clear the user details out of session storage"""
    session.clear() # Completely flushes the session cleanly
    flash("Logged out successfully.", "info")
    return redirect(url_for('main.menu'))