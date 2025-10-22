from app import app, db
from models import User # Убедитесь, что импорт правильный
from werkzeug.security import generate_password_hash
import os

with app.app_context():
    # Хэшируем пароль
    p_hash = generate_password_hash("testpass", method='pbkdf2:sha256')

    try:
        # Пытаемся создать пользователя, заполняя все необходимые поля!
        new_user_db = User(
            fullname="FinalTestUser",
            email="final@test.com",
            status='Client',
            password_hash=p_hash,
            isOnMain=False, # Добавляем булево поле, которое может быть причиной сбоя
            # ПРОВЕРЬТЕ models.py: Если есть другие поля с nullable=False, добавьте их сюда!
            # Например: field_name="default_value",
        )

        db.session.add(new_user_db)
        db.session.commit()
        print("✅ TEST USER CREATED SUCCESSFULLY IN DB!")
        print(f"ID: {new_user_db.id}")

    except Exception as e:
        # 💥 ЭТА СТРОКА ПОКАЖЕТ, ПОЧЕМУ ТЕРПИТ НЕУДАЧУ ВАША МОДЕЛЬ
        print(f"❌ CRITICAL ERROR IN MODEL CONSTRUCTOR: {e}")
        db.session.rollback()

exit() # Выход из Python-консоли