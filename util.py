from app import app, db
from models import User
from werkzeug.security import generate_password_hash
import os
import random


# Функция для генерации случайного хэша
def create_hash(password):
    # Используем метод, указанный в вашей логике
    return generate_password_hash(password, method='pbkdf2:sha256')


# Список специализаций для юристов
SPECIALIZATIONS = [
    "Tax Law", "Family Law", "Real Estate",
    "Corporate Law", "Immigration Law", "Criminal Defense"
]

with app.app_context():
    # ---------------------------------------------
    # 1. ОЧИСТКА БАЗЫ (Опционально, для чистого старта)
    # ---------------------------------------------

    # Рекомендуется, если вы часто запускаете скрипт
    # db.drop_all()
    # db.create_all()

    users_to_add = []

    # ---------------------------------------------
    # 2. АДМИНИСТРАТОР (1 пользователь)
    # ---------------------------------------------
    admin = User(
        fullname="Admin User",
        email="admin@jurist.com",
        status='Admin',
        password_hash=create_hash("adminpass"),
        balance=9999,
        isAdmin=True
    )
    users_to_add.append(admin)

    # ---------------------------------------------
    # 3. ЮРИСТЫ (5 пользователей)
    # ---------------------------------------------

    # Юристы, которых вы хотите показать на главной
    for i in range(1, 4):
        spec = random.choice(SPECIALIZATIONS)
        lawyer = User(
            fullname=f"Dr. Expert {i}",
            email=f"lawyer{i}@jurist.com",
            status='Lawyer',
            password_hash=create_hash(f"lawpass{i}"),
            balance=0,
            experience=f"{random.randint(5, 15)} years",
            specialization=spec,
            price=f"{random.randint(80, 150)}",  # Цена как строка
            description=f"Specialist in {spec} with a strong track record of success.",
            photo_url=f"photos/lawyer{i}.jpg",
            isOnMain=True
        )
        users_to_add.append(lawyer)

    # Юристы, которых нет на главной
    for i in range(4, 6):
        spec = random.choice(SPECIALIZATIONS)
        lawyer = User(
            fullname=f"Ms. Specialist {i}",
            email=f"lawyer{i}@jurist.com",
            status='Lawyer',
            password_hash=create_hash(f"lawpass{i}"),
            balance=0,
            experience=f"{random.randint(2, 7)} years",
            specialization=spec,
            price=f"{random.randint(50, 90)}",
            description=f"Experienced professional focused on {spec}.",
            photo_url=f"photos/lawyer{i}.jpg",
            isOnMain=False
        )
        users_to_add.append(lawyer)

    # ---------------------------------------------
    # 4. КЛИЕНТЫ (10 пользователей)
    # ---------------------------------------------
    for i in range(1, 11):
        client = User(
            fullname=f"Client Name {i}",
            email=f"client{i}@test.com",
            status='Client',
            password_hash=create_hash(f"clientpass{i}"),
            balance=random.randint(0, 200),  # Случайный баланс
            isOnMain=False,
            # Все поля юриста/админа оставляем None
        )
        users_to_add.append(client)

    # ---------------------------------------------
    # 5. СОХРАНЕНИЕ В БАЗУ ДАННЫХ
    # ---------------------------------------------
    try:
        db.session.add_all(users_to_add)
        db.session.commit()
        print(f"✅ SUCCESSFULLY ADDED {len(users_to_add)} USERS TO DB.")
        print(f"   5 Lawyers and 10 Clients.")

    except Exception as e:
        print(f"❌ CRITICAL ERROR DURING DATABASE SEEDING: {e}")
        db.session.rollback()

exit()