from os import execle
from flask import Flask, redirect, render_template, request, session, url_for, flash, jsonify
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from config import app, db
from models import User
from sqlalchemy import select
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

load_dotenv()


def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('You must be logged in to view this page.', 'danger')
            return redirect(url_for('login', next=request.url))

        return f(*args, **kwargs)

    return decorated_function


@app.route('/')
def index():
    print("ROUTE: Accessing index page.")
    try:
        query = db.select(User).filter(User.isOnMain == True)
        lawyers_objects = db.session.execute(query).scalars().all()
        lawyers_data = [lawyer.to_dict() for lawyer in lawyers_objects]

        print(f"✅ Lawyers loaded successfully for SSR: {len(lawyers_data)} records.")
        return render_template("index.html", lawyers=lawyers_data)

    except Exception as e:
        print(f"❌ ERROR in index route while loading lawyers: {e}")
        return render_template("index.html", lawyers=[])


@app.route('/about')
def about():
    print("ROUTE: Accessing about page.")
    return render_template("about.html")


@app.route('/lawyers')
def all_lawyers():
    print("ROUTE: Accessing all_lawyers page.")
    return render_template('lawyers.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        print("ROUTE: Rendering login form (GET).")
        return render_template('login.html')

    email = request.form.get('email')
    password = request.form.get('password')

    print(f"ROUTE: Attempting login for email: {email}")

    if not email or not password:
        print("FAIL: Missing email or password.")
        flash('Please enter both email and password.', 'danger')
        return redirect(url_for('login'))

    user = db.session.execute(select(User).filter_by(email=email)).scalar_one_or_none()

    if user and check_password_hash(user.password_hash, password):

        print(f"SUCCESS: User {user.fullname} authenticated. Status: {user.status}")

        session['username'] = user.fullname
        session['email'] = user.email
        session['status'] = user.status
        session['user_id'] = user.id


        flash(f'Welcome back, {user.fullname}!', 'success')

        if user.status == 'Admin':
            return redirect(url_for('admin_panel'))
        return redirect(f"/user/dashboard/{user.id}")

    else:
        print("FAIL: Invalid credentials (user not found or password mismatch).")
        flash('Invalid email or password.', 'danger')
        return redirect(url_for('login'))


@app.route('/sign-up', methods=["GET", "POST"])
def sign_up():
    if request.method == 'GET':
        print("ROUTE: Rendering sign-up form (GET).")
        return render_template('sign_up.html')

    fullname = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")

    print(f"ROUTE: Attempting sign-up for email: {email}")

    if not fullname or not email or not password:
        print("FAIL: Missing required sign-up data.")
        flash('Please enter all needed data.', 'danger')
        return redirect(url_for('sign_up'))

    user = db.session.execute(select(User).filter_by(email=email)).scalar_one_or_none()

    if user is not None:
        print("FAIL: Email already in use.")
        flash("This email is already used! Try logging in.", 'danger')
        return redirect(url_for('sign_up'))
    else:
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        new_user = User(
            fullname=fullname,
            email=email,
            status='Client',
            password_hash=hashed_password,
            isOnMain=False
        )

        try:
            db.session.add(new_user)
            db.session.commit()

            print(f"SUCCESS: New user created with ID: {new_user.id}")

        except Exception as e:
            print(f"❌ CRITICAL DB ERROR during sign-up: {e}")
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('sign_up'))

        session['username'] = fullname
        session['email'] = email
        session['status'] = new_user.status
        session['user_id'] = new_user.id

        flash("Registration successful and logged in!", 'success')

        return redirect(f"/user/dashboard/{new_user.id}")


@app.route('/admin')
@login_required
def admin_panel():
    print("ROUTE: Accessing admin_panel.")
    return "Admin Panel - Coming Soon"


@app.route('/user/dashboard/<int:user_id>')
@login_required
def user_dashboard(user_id):
    if session.get('user_id') != user_id:
        flash('Access denied. You can only view your own profile.', 'danger')
        return redirect(url_for('index'))

    upcoming_meetings = [
        {
            'lawyer_name': 'Dr. Alan Smith (Tax Law)',
            'date': '2025-11-05',
            'time': '14:00',
            'is_paid': True,
            'id': 101
        },
        {
            'lawyer_name': 'Ms. Jane Doe (Family Law)',
            'date': '2025-10-30',
            'time': '10:30',
            'is_paid': False,
            'id': 102
        }
    ]

    completed_meetings = [
        {
            'lawyer_name': 'Mr. Bob Johnson (Real Estate)',
            'date': '2025-09-15',
            'time': '11:00',
            'id': 95
        }
    ]

    return render_template(
        'user_dashboard.html',
        upcoming_meetings=upcoming_meetings,
        completed_meetings=completed_meetings,
        user_balance=50
    )



@app.route('/logout', methods=['POST', 'GET'])
@login_required
def logout():
    if request.method == 'POST':
        session.clear()
        flash("Logged out successfully!", 'primary')
        return redirect(url_for('login'))

    return render_template('logout.html')

with app.app_context():
    db.create_all()
    print("DB check: db.create_all() executed.")

if __name__ == '__main__':
    app.run(debug=True)