from flask import Flask
from datetime import datetime, timezone
from datetime import timedelta
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

load_dotenv()



app = Flask(__name__)
app.permanent_session_lifetime = timedelta(weeks=4)
app.secret_key = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///JuristHUB.db'
db = SQLAlchemy(app)