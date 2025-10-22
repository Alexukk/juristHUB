from config import db
from flask_sqlalchemy import SQLAlchemy


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    fullname = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(40), nullable=False, default='Client')  # 'Client', 'Lawyer', 'Admin'


    experience = db.Column(db.String(120), nullable=True)
    specialization = db.Column(db.String(120), nullable=True)
    price = db.Column(db.String(120), nullable=True)
    description = db.Column(db.String(500), nullable=True)
    photo_url = db.Column(db.String(255), nullable=True)
    isOnMain = db.Column(db.Boolean, nullable=True, default=False)


    def to_dict(self):
        return {
            'id': self.id,
            'fullname': self.fullname,
            'specialization': self.specialization,
            'description': self.description,
            'photo_url': self.photo_url,
        }