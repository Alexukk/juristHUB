from config import db
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from sqlalchemy import Numeric

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    fullname = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(40), nullable=False, default='Client')  # 'Client', 'Lawyer', 'Admin'
    balance = db.Column(db.Numeric, nullable=False)

    # Rows for lawyers

    experience = db.Column(db.String(120), nullable=True)
    specialization = db.Column(db.String(120), nullable=True)
    price = db.Column(db.String(120), nullable=True)
    description = db.Column(db.String(500), nullable=True)
    photo_url = db.Column(db.String(255), nullable=True)
    isOnMain = db.Column(db.Boolean, nullable=True, default=False)

    # Reviews

    reviews_given = db.relationship(
        'Review',
        foreign_keys='[Review.client_id]',
        back_populates='client',  # <-- Соответствует атрибуту 'client' в Review
        lazy='dynamic'
    )
    reviews_received = db.relationship(
        'Review',
        foreign_keys='[Review.lawyer_user_id]',
        back_populates='lawyer',  # <-- Соответствует атрибуту 'lawyer' в Review
        lazy='dynamic'
    )

    # Rows for admin

    isAdmin = db.Column(db.Boolean, nullable=True, default=False)

    # models.py (Предполагаемый обновленный метод)

    def to_dict_lawyer(self, rating=None, reviews_count=None):
        return {
            'id': self.id,
            'fullname': self.fullname,
            'specialization': self.specialization,
            'description': self.description,
            'photo_url': self.photo_url,

            # Конвертируем Numeric в str для Jinja2:
            'price': str(self.price) if self.price is not None else None,
            'experience': self.experience,

            'rating': float(rating) if rating is not None else None,
            'reviews_count': reviews_count if reviews_count is not None else 0
        }

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lawyer_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)

    # --- (Relationship) ---

    client = db.relationship('User', foreign_keys=[client_id], back_populates='reviews_given')
    lawyer = db.relationship('User', foreign_keys=[lawyer_user_id], back_populates='reviews_received')

    def to_dict(self):
        return {
            'id': self.id,
            'user_name': self.client.fullname,
            'lawyer_name': self.lawyer.fullname,
            'date': self.date.strftime('%Y-%m-%d'),
            'text': self.text,
            'rating': self.rating
        }

    def __repr__(self):
        return f"Review(Client ID: {self.client_id}, Lawyer ID: {self.lawyer_user_id}, Rating: {self.rating})"