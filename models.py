from config import db
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from sqlalchemy import Numeric


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    fullname = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(40), nullable=False, default='Client')
    balance = db.Column(db.Numeric, nullable=False)


    # =========================================================================
    zoom_link = db.Column(db.String(300), nullable=True)
    office_address = db.Column(db.String(300), nullable=True)
    # =========================================================================

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
        back_populates='client',
        lazy='dynamic'
    )
    reviews_received = db.relationship(
        'Review',
        foreign_keys='[Review.lawyer_user_id]',
        back_populates='lawyer',
        lazy='dynamic'
    )

    # Consultations (НОВЫЕ СВЯЗИ)
    consultations_booked = db.relationship(
        'Consultation',
        foreign_keys='[Consultation.client_id]',
        back_populates='client',
        lazy='dynamic'
    )
    consultations_as_lawyer = db.relationship(
        'Consultation',
        foreign_keys='[Consultation.lawyer_user_id]',
        back_populates='lawyer',
        lazy='dynamic'
    )

    # Rows for admin
    isAdmin = db.Column(db.Boolean, nullable=True, default=False)

    def to_dict_lawyer(self, rating=None, reviews_count=None):
        return {
            'id': self.id,
            'fullname': self.fullname,
            'specialization': self.specialization,
            'description': self.description,
            'photo_url': self.photo_url,

            'price': str(self.price) if self.price is not None else None,
            'experience': self.experience,

            # Добавьте эти поля для отображения на странице профиля, если нужно
            'zoom_link': self.zoom_link,
            'office_address': self.office_address,

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
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultation.id'), nullable=True,
                                unique=True)  # Добавлено unique=True

    # --- (Relationship) ---

    consultation = db.relationship('Consultation', back_populates='review', uselist=False,
                                   lazy='joined')  # Добавлено uselist=False
    client = db.relationship('User', foreign_keys=[client_id], back_populates='reviews_given')
    lawyer = db.relationship('User', foreign_keys=[lawyer_user_id], back_populates='reviews_received')

    def to_dict(self):
        client_name = self.client.fullname if self.client else 'Unknown Client'
        lawyer_info = ""
        if self.lawyer:
            lawyer_info = f"{self.lawyer.fullname} ({self.lawyer.specialization or 'N/A'})"

        return {
            'id': self.id,
            'user_name': client_name,
            'lawyer_name': lawyer_info,
            'date': self.date.strftime('%Y-%m-%d') if self.date else None,

            'text': self.text,
            'rating': self.rating,
            'lawyer_user_id': self.lawyer_user_id  # Добавлено для навигации
        }

    def __repr__(self):
        return f"Review(Client ID: {self.client_id}, Lawyer ID: {self.lawyer_user_id}, Rating: {self.rating})"


class Consultation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    type = db.Column(db.String(10), nullable=False)

    meeting_url = db.Column(db.String(300), nullable=True)
    location_gmaps = db.Column(db.String(300), nullable=True)

    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lawyer_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(10), nullable=False)
    payment_status = db.Column(db.String(10), nullable=False)

    client = db.relationship(
        'User',
        foreign_keys=[client_id],
        back_populates='consultations_booked',
        lazy='joined'
    )
    lawyer = db.relationship(
        'User',
        foreign_keys=[lawyer_user_id],
        back_populates='consultations_as_lawyer',
        lazy='joined'
    )
    review = db.relationship(
        'Review',
        foreign_keys='[Review.consultation_id]',
        back_populates='consultation',
        uselist=False,
        lazy='joined'
    )

    def __repr__(self):
        return f"Consultation(ID: {self.id}, Status: {self.status}, Type: {self.type})"

    def to_base_dict(self):
        return {
            'id': self.id,
            'date': self.date.strftime('%Y-%m-%d %H:%M') if self.date else None,
            'type': self.type,
            'status': self.status,
            'payment_status': self.payment_status,
            'client_id': self.client_id,
            'lawyer_id': self.lawyer_user_id,
            'review_id': self.review.id if self.review else None,
            'client_name': self.client.fullname if self.client else 'N/A',
            'lawyer_name': self.lawyer.fullname if self.lawyer else 'N/A',
        }

    def to_dict_online(self):
        data = self.to_base_dict()
        data['meeting_info'] = self.meeting_url
        data['meeting_type_label'] = 'Zoom/Online Link'
        data['meeting_icon'] = 'fas fa-video'
        return data

    def to_dict_offline(self):
        data = self.to_base_dict()
        data['meeting_info'] = self.location_gmaps
        data['meeting_type_label'] = 'Location (Google Maps)'
        data['meeting_icon'] = 'fas fa-map-marker-alt'
        return data

    def to_dict(self):
        if self.type == 'Online':
            return self.to_dict_online()
        elif self.type == 'Offline':
            return self.to_dict_offline()
        return self.to_base_dict()