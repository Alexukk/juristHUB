from flask import Flask, redirect, render_template, request, session, url_for, flash, jsonify
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from config import app
from config import db
from models import *

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

with app.app_context():
    db.create_all()
    create_test_lawyers()


if __name__ == '__main__':
    app.run(debug=True)