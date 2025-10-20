from flask import Flask, redirect, render_template, request, session, url_for, flash, jsonify
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from config import app
from config import db
from models import *
from sqlalchemy import select

load_dotenv()


# MAIN ROUTES LOGIC
@app.route('/')
def index():
    try:
        query = db.select(Lawyer).filter(Lawyer.isOnMain == True)
        lawyers_objects = db.session.execute(query).scalars().all()

        # 1. Получаем ЧИСТЫЙ список словарей
        lawyers_data = [lawyer.to_dict() for lawyer in lawyers_objects]

        print("✅ Lawyers loaded successfully for SSR")

        # 2. ПРАВИЛЬНО: Передаем ЧИСТЫЙ список 'lawyers_data' в шаблон.
        #     jsonify() НЕ используется!
        return render_template("index.html", lawyers=lawyers_data)

    except Exception as e:
        print(f"❌ An error occurred while loading lawyers for SSR: ", e)
        # В случае ошибки передаем пустой список, чтобы не сломать шаблон Jinja
        return render_template("index.html", lawyers=[])




@app.route('/about')
def about():
    return  render_template("about.html")



@app.route('/lawyers')
def all_lawyers():

    return render_template('lawyers.html')

# API LOGIC


@app.route('/api/get-main-lawyers')
def get_main_lawyers():
    try:
        query = db.select(Lawyer).filter(Lawyer.isOnMain == True)
        lawyers_objects = db.session.execute(query).scalars().all()

        lawyers_data = [lawyer.to_dict() for lawyer in lawyers_objects]
        print("Lawyers loaded successfully")
        return jsonify(lawyers=lawyers_data)
    except Exception as e:
        print(f"An error while loading lawyers: ", e)
        return jsonify(lawyers=[])


# login/register routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    email = request.form.get('email')
    password = request.form.get('password')

    if not email or not password:
        flash('Please enter both email and password.', 'danger')
        return redirect(url_for('login'))

    lawyer = db.session.execute(
        select(Lawyer).filter_by(email=email, password=password)
    ).scalar_one_or_none()

    user = lawyer

    if user:

        session['user_id'] = user.id
        session['user_status'] = user.status
        session['username'] = user.username

        flash(f'Welcome, {user.username}!', 'success')

        if user.status == 'Admin':
            return redirect(url_for('adminPanel'))
        elif user.status == 'Lawyer':
            return redirect(url_for('LawyerPanel', lawyerId=user.id))
        else:
            return redirect(url_for('ClientPanel', clientId=user.id))
    else:
        flash('Invalid email or password.', 'danger')
        return redirect(url_for('login'))


# panels logic

@app.route('/admin')
def admin_panel():

    return "Admin Panel - Coming Soon"

@app.route('/lawyer/<int:lawyer_id>/panel')
def lawyer_panel(lawyer_id):

    return f"Lawyer Panel for ID: {lawyer_id}"

@app.route('/client/<int:client_id>/panel')
def client_panel(client_id):

    return f"Client Panel for ID: {client_id}"


with app.app_context():
    db.create_all()



if __name__ == '__main__':
    app.run(debug=True)