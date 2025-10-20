from config import db
from flask_sqlalchemy import SQLAlchemy



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)



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


def create_test_lawyers():
    """Создает и добавляет в базу несколько тестовых записей Lawyer."""

    # 1. Список тестовых юристов (Добавлены обязательные поля: experience и price)
    test_lawyers = [
        Lawyer(
            name="Иванов Пётр А.",
            specialization="Семейное право",
            experience=15,  # 🚨 Добавлено обязательное поле 'experience'
            price=3000,     # 🚨 Добавлено обязательное поле 'price' (предположим, в рублях)
            description="Специализация на разводах, разделе имущества и опеке. 15 лет практики.",
            photo_url="https://via.placeholder.com/400x300.png?text=Lawyer+1",
            isOnMain=False
        ),
        Lawyer(
            name="Смирнова Ольга В.",
            specialization="Уголовное право",
            experience=10,  # 🚨 Добавлено обязательное поле
            price=5500,     # 🚨 Добавлено обязательное поле
            description="Защита по экономическим и должностным преступлениям. Высокий процент оправдательных приговоров.",
            photo_url="https://via.placeholder.com/400x300.png?text=Lawyer+2",
            isOnMain=True
        ),
        Lawyer(
            name="Алексеев Кирилл Н.",
            specialization="Корпоративное право",
            experience=7,   # 🚨 Добавлено обязательное поле
            price=4000,     # 🚨 Добавлено обязательное поле
            description="Сопровождение сделок M&A, регистрация и реорганизация бизнеса. Свободное владение английским.",
            photo_url="https://via.placeholder.com/400x300.png?text=Lawyer+3",
            isOnMain=True
        ),
        Lawyer(
            name="Петрова Мария И.",
            specialization="Недвижимость",
            experience=12,  # 🚨 Добавлено обязательное поле
            price=3500,     # 🚨 Добавлено обязательное поле
            description="Проверка юридической чистоты квартир, домов и земельных участков. Сделки под ключ.",
            photo_url="https://via.placeholder.com/400x300.png?text=Lawyer+4",
            isOnMain=True
        )
    ]

    # 2. Проверяем, есть ли уже данные
    if db.session.query(Lawyer).count() == 0:
        db.session.add_all(test_lawyers)
        db.session.commit()
        print("✅ Тестовые данные юристов успешно добавлены.")
    else:
        print("ℹ️ В базе уже есть данные, тестовые записи не добавлены.")