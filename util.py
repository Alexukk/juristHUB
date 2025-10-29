from app import app, db
from models import User, Review  # Убедитесь, что импортировали обе модели
from werkzeug.security import generate_password_hash
import random
from decimal import Decimal
from datetime import datetime, timezone # Добавим, если используется в моделях


# Функция для генерации случайного хэша
def create_hash(password):
    return generate_password_hash(password, method='pbkdf2:sha256')


# Список специализаций для юристов
SPECIALIZATIONS = [
    "Tax Law", "Family Law", "Real Estate",
    "Corporate Law", "Immigration Law", "Criminal Defense"
]

# Тексты для отзывов
GOOD_TEXT = [
    "Excellent service! Very professional and knowledgeable.",
    "Highly recommended. Solved my issue quickly and efficiently.",
    "Great experience, felt fully supported throughout the process.",
    "Five stars. The best lawyer on the platform.",
    "Clear communication and positive outcome. Couldn't ask for more."
]
BAD_TEXT = [
    "Disappointing result, communication was slow.",
    "Could be better, I expected more follow-up.",
    "Took too long to respond, service was average.",
    "Unclear on pricing and services provided.",
    "Felt rushed during the consultation."
]

# НОВЫЕ ДАННЫЕ ДЛЯ ТЕСТИРОВАНИЯ МЕСТА ВСТРЕЧИ
RICK_ROLL_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
OFFICE_ADDRESSES = [
    "100 Wall Street, New York, NY 10005",
    "750 N Dearborn St, Chicago, IL 60654",
    "350 S Grand Ave, Los Angeles, CA 90071",
    "221B Baker St, London NW1 6XE, UK",
    "1600 Pennsylvania Avenue NW, Washington, D.C. 20500"
]

with app.app_context():
    # ---------------------------------------------
    # 1. ОЧИСТКА БАЗЫ (Опционально, для чистого старта)
    # ---------------------------------------------

    # !!! РАСКОММЕНТИРУЙТЕ, ЕСЛИ НУЖНО ОЧИСТИТЬ БАЗУ !!!
    # db.drop_all()
    # db.create_all() # <-- Не забудьте создать заново!

    users_to_add = []

    # ---------------------------------------------
    # 2. АДМИНИСТРАТОР (1 пользователь)
    # ---------------------------------------------
    admin = User(
        fullname="Admin User",
        email="admin@jurist.com",
        status='Admin',
        password_hash=create_hash("adminpass"),
        balance=str(Decimal('9999.00')),
        isAdmin=True
    )
    users_to_add.append(admin)

    # ---------------------------------------------
    # 3. ЮРИСТЫ (5 пользователей)
    # ---------------------------------------------

    # Юристы с высоким рейтингом
    for i in range(1, 4):
        spec = random.choice(SPECIALIZATIONS)
        lawyer = User(
            fullname=f"Dr. Expert {i}",
            email=f"lawyer{i}@jurist.com",
            status='Lawyer',
            password_hash=create_hash(f"lawpass{i}"),
            balance=str(Decimal('0.00')),
            experience=f"{random.randint(5, 15)} years",
            specialization=spec,
            price=str(Decimal(random.randint(80, 150))),
            description=f"Specialist in {spec} with a strong track record of success.",
            photo_url=f"/static/photos/lawyer{i}.jpg",
            isOnMain=True,
            # ДОБАВЛЕНО: Ссылки для тестирования Webhook
            zoom_link=RICK_ROLL_URL,
            office_address=random.choice(OFFICE_ADDRESSES)
        )
        users_to_add.append(lawyer)

    # Юристы с низким рейтингом
    for i in range(4, 6):
        spec = random.choice(SPECIALIZATIONS)
        lawyer = User(
            fullname=f"Ms. Specialist {i}",
            email=f"lawyer{i}@jurist.com",
            status='Lawyer',
            password_hash=create_hash(f"lawpass{i}"),
            balance=str(Decimal('0.00')),
            experience=f"{random.randint(2, 7)} years",
            specialization=spec,
            price=str(Decimal(random.randint(50, 90))),
            description=f"Experienced professional focused on {spec}.",
            photo_url=f"/static/photos/lawyer{i}.jpg",
            isOnMain=False,
            # ДОБАВЛЕНО: Ссылки для тестирования Webhook
            zoom_link=RICK_ROLL_URL,
            office_address=random.choice(OFFICE_ADDRESSES)
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
            balance=str(Decimal(random.randint(0, 200))),
            isOnMain=False,
        )
        users_to_add.append(client)

    # ---------------------------------------------
    # 5. СОХРАНЕНИЕ ПОЛЬЗОВАТЕЛЕЙ В БАЗУ ДАННЫХ
    # ---------------------------------------------
    try:
        db.session.add_all(users_to_add)
        db.session.commit()
        print(f"✅ SUCCESSFULLY ADDED {len(users_to_add)} USERS TO DB.")

    except Exception as e:
        print(f"❌ CRITICAL ERROR DURING USER SEEDING: {e}")
        db.session.rollback()
        # Если вы вносили изменения в модель (как мы делали с zoom_link),
        # и не сделали миграцию, может возникнуть ошибка.
        # Попробуйте db.drop_all() / db.create_all() в начале файла.
        exit()

    # ---------------------------------------------
    # 6. НАПОЛНЕНИЕ ОТЗЫВАМИ (Review)
    # ---------------------------------------------

    # ... (код для создания отзывов не изменен) ...
    try:
        # Получаем ID всех клиентов и юристов
        client_ids = db.session.query(User.id).filter(User.status == 'Client').all()
        lawyer_ids = db.session.query(User.id).filter(User.status == 'Lawyer').all()

        client_ids = [c[0] for c in client_ids]
        lawyer_ids = [l[0] for l in lawyer_ids]

        if not client_ids or not lawyer_ids:
            print("⚠️ Skipping review creation: Not enough clients or lawyers found.")
            exit()

        reviews_to_add = []
        REVIEW_COUNT = 30

        for _ in range(REVIEW_COUNT):
            client_id = random.choice(client_ids)
            lawyer_id = random.choice(lawyer_ids)

            # Случайный рейтинг (чаще даем хорошие оценки)
            rating = random.choices([5, 4, 3, 2, 1], weights=[45, 30, 15, 5, 5], k=1)[0]

            text = random.choice(GOOD_TEXT) if rating >= 4 else random.choice(BAD_TEXT)

            new_review = Review(
                client_id=client_id,
                lawyer_user_id=lawyer_id,
                rating=rating,
                text=text + f" (Seed Review #{_ + 1})"
            )
            reviews_to_add.append(new_review)

        db.session.add_all(reviews_to_add)
        db.session.commit()
        from TimeSlotUTLIS import generate_time_slots_for_date_range
        from datetime import timedelta

        # Генерация слотов на 90 дней для всех юристов
        try:
            start_date = datetime.utcnow().date()
            end_date = start_date + timedelta(days=90)

            lawyers = User.query.filter_by(status='Lawyer').all()
            for lawyer in lawyers:
                generate_time_slots_for_date_range(lawyer, start_date, end_date)

            print(f"✅ SUCCESSFULLY GENERATED TIME SLOTS FOR {len(lawyers)} LAWYERS.")

        except Exception as e:
            print(f"❌ ERROR DURING SLOT GENERATION: {e}")
            db.session.rollback()

        print(f"✅ SUCCESSFULLY ADDED {len(reviews_to_add)} REVIEWS.")

    except Exception as e:
        print(f"❌ CRITICAL ERROR DURING REVIEW SEEDING: {e}")
        db.session.rollback()

exit()