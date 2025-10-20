from config import db
from flask_sqlalchemy import SQLAlchemy



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(120), nullable=False)


class Lawyer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    experience = db.Column(db.String(120), nullable=False)
    specialization = db.Column(db.String(120), nullable=False)
    price = db.Column(db.String(120), nullable=False) # per hour
    description = db.Column(db.String(120), nullable=False)
    photo_url = db.Column(db.String(120), nullable=False)
    isOnMain = db.Column(db.Boolean, nullable=False)

    def to_dict(self):

        return {
            'id': self.id,
            'name': self.name,
            'specialization': self.specialization,
            'description': self.description,
            'photo_url': self.photo_url,
        }

