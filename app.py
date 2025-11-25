from http import HTTPStatus

from flask import Flask, redirect, render_template, request, session, url_for, flash, jsonify
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from config import app, db
from models import User, Consultation, TimeSlot
from sqlalchemy import select
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import cast, Numeric, distinct
from models import User, Review, Consultation
from sqlalchemy import func, case, text
import stripe
from datetime import date, timedelta
from decimal import Decimal, getcontext
from telebot import TeleBot
from datetime import datetime, time
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, desc, asc
from collections import defaultdict
from sqlalchemy.orm import joinedload

load_dotenv()
getcontext().prec = 10
PLATFORM_COMMISSION_RATE = Decimal('0.10')
bot = TeleBot(os.getenv('TELEGRAM_API_KEY'))
chat_id = os.getenv('CHAT_ID')

stripe.api_key = os.getenv("STRIPE_TEST_PRIVATE")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('You must be logged in to view this page.', 'danger')
            return redirect(url_for('login', next=request.url))

        return f(*args, **kwargs)

    return decorated_function


def process_consultation_data(consultation, user_model, current_time):

    lawyer = db.session.get(user_model, consultation.lawyer_user_id)
    lawyer_name = lawyer.fullname if lawyer else "Unknown Lawyer"

    meeting_data = {
        'id': consultation.id,
        'date': consultation.date.strftime('%Y-%m-%d') if consultation.date else 'N/A',
        'time': consultation.time.strftime('%H:%M') if consultation.time else 'N/A',
        'lawyer_name': lawyer_name,
        'status': consultation.status,
        'payment_status': consultation.payment_status,
        'is_paid': consultation.payment_status == 'paid' or consultation.payment_status == 'refunded',

        # КРИТИЧЕСКОЕ ПОЛЕ ДЛЯ КНОПКИ ОТЗЫВА
        'has_review': consultation.review is not None
    }

    # 3. Логика сортировки
    if consultation.status == 'cancelled':
        return 'cancelled', meeting_data
    elif consultation.status == 'completed':
        return 'completed', meeting_data
    elif consultation.date and consultation.date.replace(tzinfo=timezone.utc) > current_time:
        return 'upcoming', meeting_data
    else:
        return 'completed', meeting_data




@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404


@app.route('/')
def index():
    print("ROUTE: Accessing index page.")

    try:
        avg_rating = func.avg(Review.rating).label('average_rating')
        count_reviews = func.count(Review.id).label('review_count')


        query = (
            db.select(
                User,
                avg_rating,
                count_reviews
            )
            .filter(User.status == 'Lawyer', User.isOnMain == True)
            .join(Review, User.id == Review.lawyer_user_id, isouter=True)
            .group_by(User.id)
            .order_by(text('average_rating DESC NULLS LAST'), User.id.asc())
        )

        results = db.session.execute(query).all()
        lawyers_data = []
        for lawyer_obj, rating_val, count_val in results:

            data = lawyer_obj.to_dict_lawyer(rating=rating_val, reviews_count=count_val)
            lawyers_data.append(data)

        print(f"✅ Lawyers loaded successfully for SSR: {len(lawyers_data)} records.")
        return render_template("index.html", lawyers=lawyers_data)
    except Exception as e:
        print(f"❌ CRITICAL ERROR in index route while loading lawyers: {e}")
        return render_template("index.html", lawyers=[])

@app.route('/about')
def about():
    print("ROUTE: Accessing about page.")
    return render_template("about.html")


@app.route('/lawyers', methods=['GET'])
def all_lawyers():
    avg_rating = func.avg(Review.rating).label('average_rating')
    count_reviews = func.count(Review.id).label('review_count')

    query = (
        db.select(
            User,
            avg_rating,
            count_reviews
        )
        .filter(User.status == 'Lawyer')

        .join(Review, User.id == Review.lawyer_user_id, isouter=True)

        .group_by(User.id)
    )


    specialty_filter = request.args.get('specialty')
    if specialty_filter:
        query = query.filter(User.specialization == specialty_filter)


    sort_by = request.args.get('sort_by')

    if sort_by == 'price_asc':

        query = query.order_by(cast(User.price, Numeric).asc())
    elif sort_by == 'price_desc':

        query = query.order_by(cast(User.price, Numeric).desc())
    else:

        query = query.order_by(text('average_rating DESC NULLS LAST'), User.id.asc())


    results = db.session.execute(query).all()


    lawyers_data = []
    for lawyer_obj, rating_val, count_val in results:
        data = lawyer_obj.to_dict_lawyer(rating=rating_val, reviews_count=count_val)
        lawyers_data.append(data)


    unique_specialties_query = db.session.query(
        distinct(User.specialization)
    ).filter(
        User.specialization.isnot(None),
        User.status == 'Lawyer'
    ).all()
    unique_specialties = [s[0] for s in unique_specialties_query if s[0]]

    return render_template('all_lawyers.html',
                           all_lawyers=lawyers_data,
                           unique_specialties=unique_specialties)


@app.route('/reviews')
def reviews():
    print("ROUTE: Accessing reviews page, loading from DB.")

    # 1. Получение параметров сортировки и фильтрации из URL
    # 'newest' по умолчанию
    sort_by = request.args.get('sort_by', 'newest')
    # '0' (все) по умолчанию
    min_rating = int(request.args.get('min_rating', 0))

    try:
        # --- БЛОК СТАТИСТИКИ (игнорирует фильтрацию) ---

        # Общая статистика (средний рейтинг и распределение) - требуется для боковой панели
        total_reviews = db.session.query(Review).count()
        average_rating = db.session.query(func.avg(Review.rating)).scalar()

        # Распределение звезд (например, [(5, 120), (4, 50), ...])
        rating_counts = db.session.query(Review.rating, func.count(Review.rating)) \
            .group_by(Review.rating).all()

        # Преобразование в словарь для шаблона {5: 120, 4: 50, ...}
        rating_distribution = defaultdict(int, dict(rating_counts))

        # --- БЛОК ОСНОВНОГО ЗАПРОСА (с фильтрацией и сортировкой) ---

        # 2. Формирование запроса с фильтрацией по минимальному рейтингу
        query = (
            db.select(Review)
            .filter(Review.rating >= min_rating)
            .options(
                joinedload(Review.client),
                joinedload(Review.lawyer)
            )
        )

        # 3. Применение сортировки
        if sort_by == 'newest':
            query = query.order_by(desc(Review.date))
        elif sort_by == 'highest':
            query = query.order_by(desc(Review.rating), desc(Review.date))
        elif sort_by == 'lowest':
            query = query.order_by(asc(Review.rating), desc(Review.date))

        reviews_objects = db.session.execute(query).scalars().all()

        # 4. Преобразование в словарь (должно быть определено в Review.to_dict())
        reviews_list = [
            review.to_dict() for review in reviews_objects
        ]

        print(f"✅ Loaded {len(reviews_list)} filtered reviews.")

        return render_template(
            'reviews.html',
            reviews=reviews_list,
            total_reviews=total_reviews,
            average_rating=average_rating,
            rating_distribution=rating_distribution
        )

    except Exception as e:
        print(f"❌ ERROR loading reviews from DB: {e}")
        return render_template('reviews.html',
                               reviews=[],
                               total_reviews=0,
                               average_rating=0,
                               rating_distribution=defaultdict(int))


@app.route('/support', methods=['POST', 'GET'])
def support():
    if request.method == 'POST':
        if not session['email']:
            flash('You must be logged in to contact support')
            return redirect(url_for('login'))

        user_email = request.form.get('user_email')
        problem_type = request.form.get('problem_type')
        problem_description = request.form.get('problem_description')
        contact_phone = ''
        if request.form.get('contact_phone'):
            contact_phone = request.form.get('contact_phone')
        try:
            message = (
                f"🚨 NEW SUPPORT REQUEST\n"
                f"----------------------------------------\n"
                f"👤 User Details:\n"
                f"  ID: {session.get('user_id', 'N/A')}\n"
                f"  Name: {session.get('username', 'N/A')}\n"
                f"  Email (from form): {user_email}\n"
                f"----------------------------------------\n"
                f"❓ Request Details:\n"
                f"  Type: {problem_type.upper()}\n"
                f"  Phone: {contact_phone if contact_phone else 'Not provided'}\n"
                f"----------------------------------------\n"
                f"📝 Description:\n"
                f"{problem_description}"
            )

            bot.send_message(chat_id, message)
            flash('Request sent, we will answer as soon as possible!', 'success')
            return render_template('support_page.html')
        except Exception as e:
            print(e)
            flash("We have troubles sending your data try again later.", 'error')
            return redirect(url_for('support'))

    return render_template('support_page.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        print("ROUTE: Rendering login form (GET).")
        return render_template('login.html')

    email = request.form.get('email')
    password = request.form.get('password')

    print(f"ROUTE: Attempting login for email: {email}")

    if not email or not password:
        print("FAIL: Missing email or password.")
        flash('Please enter both email and password.', 'danger')
        return redirect(url_for('login'))

    user = db.session.execute(select(User).filter_by(email=email)).scalar_one_or_none()

    if user and check_password_hash(user.password_hash, password):

        print(f"SUCCESS: User {user.fullname} authenticated. Status: {user.status}")

        session['username'] = user.fullname
        session['email'] = user.email
        session['status'] = user.status
        session['user_id'] = user.id
        session['balance'] = user.balance


        flash(f'Welcome back, {user.fullname}!', 'success')

        if user.status == 'Lawyer':
            return redirect(url_for('lawyer_dashboard'))
        return redirect(url_for('user_dashboard', user_id=user.id))

    else:
        print("FAIL: Invalid credentials (user not found or password mismatch).")
        flash('Invalid email or password.', 'danger')
        return redirect(url_for('login'))


@app.route('/sign-up', methods=["GET", "POST"])
def sign_up():
    if request.method == 'GET':
        print("ROUTE: Rendering sign-up form (GET).")
        return render_template('sign_up.html')

    fullname = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")

    print(f"ROUTE: Attempting sign-up for email: {email}")

    if not fullname or not email or not password:
        print("FAIL: Missing required sign-up data.")
        flash('Please enter all needed data.', 'danger')
        return redirect(url_for('sign_up'))

    user = db.session.execute(select(User).filter_by(email=email)).scalar_one_or_none()

    if user is not None:
        print("FAIL: Email already in use.")
        flash("This email is already used! Try logging in.", 'danger')
        return redirect(url_for('sign_up'))
    else:
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        new_user = User(
            fullname=fullname,
            email=email,
            status='Client',
            password_hash=hashed_password,
            isOnMain=False,
            balance = 0
        )

        try:
            db.session.add(new_user)
            db.session.commit()

            print(f"SUCCESS: New user created with ID: {new_user.id}")

        except Exception as e:
            print(f"❌ CRITICAL DB ERROR during sign-up: {e}")
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('sign_up'))

        session['username'] = fullname
        session['email'] = email
        session['status'] = new_user.status
        session['user_id'] = new_user.id
        session['balance'] = 0

        flash("Registration successful and logged in!", 'success')

        return redirect(url_for('user_dashboard', user_id=session['user_id']))


@app.route('/lawyer/dashboard', methods=['GET', 'POST'])
def lawyer_dashboard():
    lawyer_id = session.get('user_id')
    lawyer_status = session.get('status')

    if not lawyer_id or lawyer_status != 'Lawyer':
        flash('Access denied. Please log in as a lawyer.', 'danger')
        return redirect(url_for('login'))

    lawyer = db.session.execute(select(User).filter_by(id=lawyer_id)).scalar_one_or_none()

    if not lawyer:
        session.clear()
        flash('Authentication Error. Please try logging in again.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        consultation_id = request.form.get('timeslot_id')
        new_status = request.form.get('new_status')

        consultation = db.session.get(Consultation, consultation_id)

        if consultation and consultation.lawyer_user_id == lawyer_id:
            consultation.status = new_status
            db.session.commit()
            flash(f'Consultation No.{consultation_id} status updated to "{new_status}".', 'success')
        else:
            flash('Error: Consultation not found or does not belong to you.', 'danger')

        return redirect(url_for('lawyer_dashboard'))

    base_filter = Consultation.lawyer_user_id == lawyer_id

    preparing_slots = Consultation.query.filter(
        base_filter,
        Consultation.status.in_(['pending', 'confirmed'])
    ).order_by(Consultation.date.asc()).all()

    completed_slots = Consultation.query.filter(
        base_filter,
        Consultation.status == 'completed'
    ).order_by(Consultation.date.desc()).limit(10).all()

    cancelled_slots = Consultation.query.filter(
        base_filter,
        Consultation.status == 'cancelled'
    ).order_by(Consultation.date.desc()).limit(10).all()

    return render_template('lawyer_dashboard.html',
                           lawyer=lawyer,
                           preparing_slots=preparing_slots,
                           completed_slots=completed_slots,
                           cancelled_slots=cancelled_slots)

@app.route('/admin')
@login_required
def admin_panel():
    print("ROUTE: Accessing admin_panel.")
    return "Admin Panel - Coming Soon"


@app.route('/lawyer/<int:lawyer_id>')
def lawyer_page(lawyer_id):
    print(f"ROUTE: Accessing profile for Lawyer ID: {lawyer_id}")

    try:

        avg_rating = func.avg(Review.rating).label('average_rating')
        count_reviews = func.count(Review.id).label('review_count')

        query = (
            db.select(User, avg_rating, count_reviews)
            .filter(User.id == lawyer_id, User.status == 'Lawyer')
            # LEFT JOIN для включения юристов без отзывов
            .join(Review, User.id == Review.lawyer_user_id, isouter=True)
            .group_by(User.id)
        )

        result = db.session.execute(query).first()

        if not result:
            print(f"FAIL: Lawyer ID {lawyer_id} not found.")
            return "Error 404: Lawyer not found.", 404

        lawyer_obj, rating_val, count_val = result

        lawyer_data = lawyer_obj.to_dict_lawyer(
            rating=rating_val,
            reviews_count=count_val
        )


        reviews_query = (
            db.select(Review)
            .filter(Review.lawyer_user_id == lawyer_id)
            .options(db.joinedload(Review.client))
            .order_by(Review.date.desc())
        )

        reviews_objects = db.session.execute(reviews_query).scalars().all()

        reviews_list = [review.to_dict() for review in reviews_objects]

        print(f"✅ Lawyer profile loaded: {lawyer_data['fullname']}, Reviews shown: {len(reviews_list)}")
        today_date_str = date.today().isoformat()
        return render_template(
            'lawyer_profile.html',
            lawyer=lawyer_data,
            reviews=reviews_list,
            today_date=today_date_str
        )

    except Exception as e:
        print(f"❌ CRITICAL ERROR accessing lawyer profile: {e}")
        return "Internal Server Error", 500


@app.route('/lawyer/<int:lawyer_id>/availability')
def get_availability(lawyer_id):
    date_str = request.args.get('date')

    if not date_str:
        return jsonify([])

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Expected YYYY-MM-DD'}), 400

    # Получаем текущее время в UTC для всех сравнений
    current_datetime_utc = datetime.now(timezone.utc)
    current_date_utc = current_datetime_utc.date()

    # --- 1. Ограничение: Проверка на 3 месяца вперед ---
    three_months_ahead = current_date_utc + timedelta(days=90)

    if selected_date > three_months_ahead:
        return jsonify({'error': 'Booking is restricted to 90 days in advance.'}), 400

    # Также блокируем просмотр прошедших дней, чтобы избежать запросов на слоты,
    # которые уже должны быть удалены или помечены как expired
    if selected_date < current_date_utc:
        return jsonify({'error': 'Cannot view past days availability.'}), 400

    # Определяем начало и конец выбранного дня для запроса к БД
    # В БД слоты хранятся как наивные объекты (без tzinfo), поэтому запрашиваем без tzinfo
    start_dt = datetime.combine(selected_date, time.min)
    end_dt = datetime.combine(selected_date, time.max)

    # 2. Получаем все слоты для выбранного дня
    slots = TimeSlot.query.filter(
        TimeSlot.lawyer_id == lawyer_id,
        TimeSlot.slot_datetime >= start_dt,
        TimeSlot.slot_datetime <= end_dt
    ).order_by(TimeSlot.slot_datetime).all()

    all_slots_with_status = []

    for slot in slots:
        # Устанавливаем временную зону UTC для сравнения.
        slot_dt_utc = slot.slot_datetime.replace(tzinfo=timezone.utc)

        # Начальный статус берем из БД (available, booked, pending...)
        display_status = slot.status

        # 3. Логика: Прошедшие слоты
        if slot_dt_utc < current_datetime_utc:
            # Слот, который уже прошел, помечаем как 'expired'
            display_status = 'expired'

        # Возвращаем статус: 'available' (доступно), 'booked' (занято), 'expired' (прошло)
        all_slots_with_status.append({
            'time': slot.slot_datetime.strftime('%H:%M'),
            'status': display_status
        })

    # Возвращаем полный список слотов с актуальными статусами
    return jsonify(all_slots_with_status)


@app.route('/dashboard/<int:user_id>')
# @login_required # Assuming this decorator is defined
def user_dashboard(user_id):
    # 1. Проверка, что пользователь просматривает свой дашборд
    if session.get('user_id') != user_id and session.get('status') != 'Admin':
        flash('You are not authorized to view this dashboard.', 'danger')
        return redirect(url_for('index'))

    # --- ДОБАВЛЕНИЕ ЛОГИКИ ОБНОВЛЕНИЯ БАЛАНСА В СЕССИИ ---

    # 1. Получаем пользователя из базы данных
    current_user = None
    try:
        current_user = db.session.query(User).filter_by(id=user_id).first()
    except Exception as e:
        print(f"Database error fetching user {user_id}: {e}")
        flash("Internal server error fetching user data.", "danger")
        return redirect(url_for('index'))

    if current_user:
        # 2. Обновляем 'balance' в сессии свежим значением из БД
        # Баланс хранится как Decimal, преобразуем его в строку для удобного хранения в сессии
        session['balance'] = str(current_user.balance)

        # NOTE: Если нужно, здесь можно обновить и другие поля
    # -----------------------------------------------------------

    # Получаем все консультации, где текущий пользователь - клиент
    client_consultations = Consultation.query.filter_by(client_id=user_id).all()

    # Устанавливаем текущее время в UTC для сравнения
    now = datetime.now(timezone.utc)

    # --- ЛОГИКА СОРТИРОВКИ И ОПРЕДЕЛЕНИЯ СТАТУСА КОНСУЛЬТАЦИЙ ---

    # 1. Предстоящие (Upcoming)
    upcoming_meetings = [
        c.to_dict(include_lawyer=True) for c in client_consultations
        if c.status not in ['completed', 'cancelled'] and \
           c.date and (c.date.replace(tzinfo=timezone.utc) + timedelta(hours=1)) > now
    ]

    # 2. Завершенные (Completed)
    completed_meetings = [
        c.to_dict(include_lawyer=True) for c in client_consultations
        if c.status == 'completed' or \
           (c.status not in ['cancelled'] and c.date and (
                   c.date.replace(tzinfo=timezone.utc) + timedelta(hours=1)) <= now)
    ]

    # 3. Отмененные
    cancelled_meetings = [
        c.to_dict(include_lawyer=True) for c in client_consultations
        if c.status == 'cancelled'
    ]

    return render_template(
        'user_dashboard.html',
        upcoming_meetings=upcoming_meetings,
        completed_meetings=completed_meetings,
        cancelled_meetings=cancelled_meetings,
        # Передаем обновленный баланс во фронтенд (если нужно отобразить его отдельно от сессии)
        user_balance=session.get('balance', '0.00')
    )

@app.route("/add-review/<int:consultation_id>", methods=['POST'])
@login_required
def add_review(consultation_id):
    # Получаем ID клиента. Используем current_user, если Flask-Login настроен.
    client_id = session.get('user_id')

    if request.method == 'POST':
        rating_str = request.form.get('rating')
        text = request.form.get('text', '').strip()  # Получаем текст, удаляя пробелы

        try:
            rating = int(rating_str)
            if not (1 <= rating <= 5):
                flash('Rating must be between 1 and 5 stars.', 'danger')
                return redirect(url_for('user_dashboard', user_id=client_id))
        except (TypeError, ValueError):
            flash('Invalid rating provided.', 'danger')
            return redirect(url_for('user_dashboard', user_id=client_id))

        # 2. Проверка консультации и прав
        consultation = db.session.get(Consultation, consultation_id)

        if not consultation:
            flash('Consultation not found.', 'danger')
            return redirect(url_for('user_dashboard', user_id=client_id))

        if consultation.client_id != client_id:
            flash('You are not authorized to review this consultation.', 'danger')
            return redirect(url_for('user_dashboard', user_id=client_id))

        if consultation.status != 'completed':
            flash('Review can only be added to completed consultations.', 'danger')
            return redirect(url_for('user_dashboard', user_id=client_id))

        if consultation.review:
            flash('You have already reviewed this consultation.', 'warning')
            return redirect(url_for('user_dashboard', user_id=client_id))

        try:
            new_review = Review(
                consultation_id=consultation_id,
                lawyer_user_id=consultation.lawyer_user_id,
                client_id=client_id,
                rating=rating,
                text=text,
                date=datetime.utcnow()  # Используйте datetime.now(timezone.utc) если настроено
            )

            db.session.add(new_review)

            # 4. Обновление среднего рейтинга юриста
            lawyer = db.session.get(User, consultation.lawyer_user_id)
            if lawyer:
                # Получаем все отзывы, включая только что добавленный
                all_reviews = Review.query.filter_by(lawyer_user_id=lawyer.id).all()

                total_rating = sum(r.rating for r in all_reviews)
                count = len(all_reviews)

                if count > 0:
                    lawyer.rating = round(total_rating / count, 2)  # Обновляем средний рейтинг
                    lawyer.reviews_count = count  # Обновляем счетчик
                    db.session.add(lawyer)

            db.session.commit()

            flash('Thank you! Your review has been successfully submitted.', 'success')

        except IntegrityError:
            db.session.rollback()
            flash('Database error: This consultation may have already been reviewed.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'An unexpected error occurred: {e}', 'danger')

        return redirect(url_for('user_dashboard', user_id=client_id))

    # Если запрос GET (что не должно происходить), просто редирект
    return redirect(url_for('user_dashboard', user_id=client_id))


@app.route('/logout', methods=['POST', 'GET'])
@login_required
def logout():
    if request.method == 'POST':
        session.clear()
        flash("Logged out successfully!", 'primary')
        return redirect(url_for('login'))

    return render_template('logout.html')


@app.route('/edit-profile/<int:user_id>', methods=['POST', 'GET'])
@login_required
def edit_profile(user_id):
    # 1. Проверка прав доступа: Пользователь может редактировать только свой профиль или быть Админом
    if session.get('user_id') != user_id and session.get('status') != 'Admin':
        flash("You can't edit details of another user.", "danger")
        return redirect(url_for('index'))

    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('index'))

    # --- GET-запрос: Рендеринг шаблона ---
    if request.method == 'GET':
        # Передаем объект user в шаблон для заполнения полей
        return render_template('edit-profile.html', user=user)

        # --- POST-запрос: Обработка формы ---
    else:
        # ОБЩИЕ ПОЛЯ (для всех пользователей)
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        try:
            user.username = username
            user.email = email

            if password:
                if password != confirm_password:
                    flash('New password and confirmation do not match.', 'warning')
                    return redirect(url_for('edit_profile', user_id=user_id))

                user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

            if user.status == 'Lawyer':
                new_price = request.form.get('price', type=float)
                new_description = request.form.get('description')
                # НОВЫЕ ПОЛЯ: Zoom Link и Office Address
                new_zoom_link = request.form.get('zoom_link')
                new_office_address = request.form.get('office_address')

                if new_price is None or new_price <= 0:
                    flash('Consultation Price must be a positive number.', 'warning')
                    return redirect(url_for('edit_profile', user_id=user_id))

                user.price = new_price
                user.description = new_description
                user.zoom_link = new_zoom_link  # Сохранение новой ссылки Zoom
                user.office_address = new_office_address  # Сохранение нового адреса офиса

            db.session.commit()

            session['email'] = user.email
            session['username'] = user.username

            flash('Your account details have been successfully updated! ✨', 'success')

        except Exception as e:
            db.session.rollback()
            print('An error occured while changing profile info: \n', e)
            flash('An error occurred while updating the profile.', 'danger')
            return redirect(url_for('edit_profile', user_id=user_id))

    return redirect(url_for('user_dashboard', user_id=user_id))




@app.route('/consultation/<int:lawyer_id>/checkout', methods=['POST', 'GET'])
# @login_required # Оставляем, если он у вас определен
def payment_provider(lawyer_id):
    if request.method == 'POST':
        client_id = session.get('user_id')
        if not client_id:
            return redirect(url_for('login_route'))

        date_str = request.form.get('booking_date')
        time_str = request.form.get('booking_time')
        consultation_type = request.form.get('type', 'Online')

        lawyer = db.session.get(User, lawyer_id)
        if not lawyer or lawyer.status != 'Lawyer':
            return "Lawyer not found or is inactive", 404

        if not date_str or not time_str:
            # print("Missing date or time in form data.")
            return "Missing required date or time for booking.", 400

        if lawyer.price is None:
            # print(f"Price is missing for lawyer ID {lawyer_id}.")
            return "Consultation price is not set for this lawyer.", 400

        try:
            price_usd = float(lawyer.price)
            consultation_price_cents = int(price_usd * 100)

            booking_datetime = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M').replace(
                tzinfo=timezone.utc)

        except (ValueError, TypeError) as e:
            # Ловит ошибки, если цена не число или datetime неверного формата
            # print(f"Data conversion error (price or datetime format): {e}")
            return f"Invalid data (price or datetime format): {e}", 500

        # 🔍 Проверка слота
        slot = TimeSlot.query.filter_by(
            lawyer_id=lawyer_id,
            slot_datetime=booking_datetime,
            status='available'
        ).first()

        if not slot:
            return "Selected time slot is not available", 400

        # 📍 Локация
        meeting_url = lawyer.zoom_link if consultation_type == 'Online' else None
        location_gmaps = lawyer.office_address if consultation_type == 'Offline' else None

        # 📝 Создание консультации (В критической секции с обработкой ошибок)
        try:
            new_consultation = Consultation(
                client_id=client_id,
                lawyer_user_id=lawyer_id,
                date=booking_datetime,
                type=consultation_type,
                status='pending',
                payment_status='unpaid',
                meeting_url=meeting_url,
                location_gmaps=location_gmaps,
                price=price_usd,
                time_slot_id=slot.id
            )
            db.session.add(new_consultation)
            db.session.flush()

            # 🔒 Блокировка слота
            slot.status = 'booked'
            slot.consultation_id = new_consultation.id
            db.session.add(slot)
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            # print(f"Database error during slot reservation: {e}")
            return "Server error while reserving slot.", 500

        # 💳 Stripe Checkout
        try:
            stripe_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': f'Consultation with {lawyer.fullname}',
                            'description': f'Type: {consultation_type} on {date_str} at {time_str}',
                        },
                        'unit_amount': consultation_price_cents,
                    },
                    'quantity': 1,
                }],
                mode='payment',
                metadata={'consultation_id': new_consultation.id},
                success_url=url_for('payment_success', _external=True) + '?consultation_id=' + str(new_consultation.id),
                cancel_url=url_for('payment_canceled', _external=True) + '?consultation_id=' + str(new_consultation.id),
            )
            return redirect(stripe_session.url)

        except Exception as e:
            # print(f"Stripe session creation failed: {e}")
            flash('Payment system error. Please try again.', 'danger')
            return redirect(url_for('lawyer_profile', lawyer_id=lawyer_id))  # Перенаправить обратно на профиль

    return redirect('/')


@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('stripe-signature')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:

        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:

        return jsonify({'error': 'Invalid signature'}), 400

    # 2. Обработка типа события
    if event['type'] == 'checkout.session.completed':
        session_data = event['data']['object']


        consultation_id = session_data.get('metadata', {}).get('consultation_id')

        if consultation_id:
            try:
                consultation = db.session.get(Consultation, int(consultation_id))

                if consultation and consultation.payment_status == 'unpaid':


                    lawyer = db.session.get(User, consultation.lawyer_user_id)

                    if lawyer:

                        if consultation.type == 'Online':
                            consultation.meeting_url = lawyer.zoom_link
                            location_info = f"Online link set: {lawyer.zoom_link}"


                        elif consultation.type == 'Offline':
                            consultation.location_gmaps = lawyer.office_address
                            location_info = f"Office address set: {lawyer.office_address}"
                        else:
                            location_info = "Consultation type unknown, no location set."
                    else:
                        location_info = "Error: Lawyer not found to set location."


                    consultation.payment_status = 'paid'
                    consultation.status = 'scheduled'

                    db.session.commit()

                    # 📧 TODO: Отправить уведомления юристу и клиенту
                    print(f"WEBHOOK SUCCESS: Consultation {consultation_id} marked as PAID. {location_info}")

            except Exception as db_error:
                db.session.rollback()
                return jsonify({'message': f'DB Error: {db_error}'}), 500

    return jsonify({'status': 'success'}), 200


@app.route('/consultation/payment/success')
def payment_success():
    consultation_id = request.args.get('consultation_id')

    try:
        consultation = db.session.get(Consultation, int(consultation_id))
    except (TypeError, ValueError):
        return "Error: Invalid Consultation ID.", 400

    if not consultation:
        return "Error: Booking not found.", 404

    if consultation.payment_status != 'paid':
        try:
            lawyer = db.session.get(User, consultation.lawyer_user_id)
            if not lawyer:

                print(f"CRITICAL: Lawyer ID {consultation.lawyer_user_id} not found for commission.")

            full_price = Decimal(lawyer.price) if lawyer else Decimal('0.00')

            earnings = full_price * (Decimal('1.00') - PLATFORM_COMMISSION_RATE)


            consultation.payment_status = 'paid'
            consultation.status = 'scheduled'


            if lawyer:
                lawyer.balance += earnings
                db.session.add(lawyer)
                print(
                    f"💰 SUCCESS: Consultation {consultation_id} paid. Lawyer {lawyer.fullname} earned ${earnings:.2f}")

            db.session.add(consultation)
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            print(f"❌ DB/Commission Error in payment_success: {e}")
            return f"Internal Server Error during finalization: {e}", 500


    flash('Payment successful! Your consultation is now confirmed.', 'success')
    return redirect(url_for('consultation_details', consultation_id=consultation_id))


@app.route('/consultation/payment/cancel')
def payment_canceled():
    return render_template('payment_failed.html')


@app.route('/consultation/<int:consultation_id>', methods=['GET', 'POST'])
@login_required
def consultation_details(consultation_id):
    # 1. Извлечение ID и статуса из сессии (Устраняет ошибку NameError: current_user)
    current_user_id = session.get('user_id')
    current_user_status = session.get('status', 'User')

    if not current_user_id:
        return redirect(url_for('login_route'))  # Предполагаемый маршрут входа

    # 2. Получение консультации
    consultation = db.session.get(Consultation, consultation_id)

    if not consultation:
        flash('Consultation not found.', 'danger')
        # Устраняет ошибку BuildError: url_for('user_dashboard') требует user_id
        return redirect(url_for('user_dashboard', user_id=current_user_id))

        # 3. Проверка прав доступа
    is_client = consultation.client_id == current_user_id
    is_lawyer = consultation.lawyer_user_id == current_user_id
    is_admin = current_user_status == 'Admin'

    if not (is_client or is_lawyer or is_admin):
        flash('You do not have access to this consultation.', 'danger')
        return redirect(url_for('user_dashboard', user_id=current_user_id))

    # --- Обработка POST-запроса (Отмена) ---
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'cancel' and (is_client or is_admin):

            # Дополнительная проверка: нельзя отменить уже завершенную или отмененную
            if consultation.status in ['cancelled', 'completed']:
                flash(f'Cannot cancel consultation. Status is already "{consultation.status}".', 'warning')
                return redirect(url_for('consultation_details', consultation_id=consultation_id))

            try:
                # --- ЛОГИКА ТРАНЗАКЦИЙ ---

                consultation_price = Decimal(str(consultation.price))

                # 1. ОБНОВЛЕНИЕ СТАТУСА СЛОТА (КРИТИЧЕСКИЙ БЛОК ДЛЯ ОСВОБОЖДЕНИЯ)
                if consultation.time_slot_id:
                    timeslot = db.session.get(TimeSlot, consultation.time_slot_id)

                    if timeslot:
                        # 1.1. ОСВОБОЖДАЕМ СТАТУС ЯЧЕЙКИ
                        timeslot.status = 'available'

                        # 1.2. ОЧИЩАЕМ ОБРАТНУЮ СВЯЗЬ
                        timeslot.consultation_id = None

                        db.session.add(timeslot)

                # 2. ФИНАНСОВЫЕ ОПЕРАЦИИ
                if consultation.payment_status == 'paid':

                    # 2.1. Возврат средств клиенту
                    client = db.session.get(User, consultation.client_id)
                    if client:
                        client.balance += consultation_price
                        if current_user_id == client.id:
                            session['balance'] = float(client.balance)
                        flash(f'Consultation cancelled. ${consultation_price:.2f} refunded to your balance.', 'success')
                        consultation.payment_status = 'refunded'
                    else:
                        consultation.payment_status = 'refund_pending_manual'
                        flash('Consultation cancelled, but client record missing. Manual refund needed.', 'danger')

                    # 2.2. Снятие комиссии с баланса юриста
                    lawyer = db.session.get(User, consultation.lawyer_user_id)
                    if lawyer:
                        earnings_to_reverse = consultation_price * (Decimal('1.00') - PLATFORM_COMMISSION_RATE)
                        lawyer.balance -= earnings_to_reverse
                        if lawyer.balance < 0:
                            lawyer.balance = Decimal('0.00')
                            flash(f'Warning: Lawyer {lawyer.fullname} balance adjusted due to refund reversal.',
                                  'warning')

                elif consultation.payment_status == 'unpaid':
                    flash('Consultation cancelled successfully. No refund necessary as payment was pending.', 'success')

                # 3. Фиксация статуса консультации и очистка прямой связи
                consultation.status = 'cancelled'
                consultation.time_slot_id = None
                db.session.add(consultation)

                # 4. ФИНАЛЬНЫЙ КОММИТ
                db.session.commit()

            except Exception:
                db.session.rollback()
                flash('Database error during cancellation commit. Transaction rolled back.', 'danger')
            except Exception as e:
                db.session.rollback()
                flash(f'An unexpected error occurred: {e}', 'danger')

            # Успешный редирект (Устраняет ошибку BuildError)
            return redirect(url_for('user_dashboard', user_id=current_user_id))

    # --- Обработка GET-запроса (Отображение деталей) ---

    consultation_data = consultation.to_dict()
    # Убедитесь, что 'consultation.date' — это объект, который можно преобразовать в isoformat
    consultation_data['js_date_iso'] = consultation.date.isoformat() if hasattr(consultation, 'date') else None

    lawyer = db.session.get(User, consultation.lawyer_user_id)
    lawyer_name = lawyer.fullname if lawyer else "Unknown Lawyer"

    return render_template(
        'consultation_details.html',
        consultation=consultation_data,
        lawyer_name=lawyer_name,
        is_client=is_client,
        is_lawyer=is_lawyer
    )


@app.route('/lawyer/slots/manage', methods=['GET'])
@login_required
def manage_slots():
    lawyer_id = session.get('user_id')

    if not lawyer_id:
        flash('Please log in as lawyer to manage your schedule.', 'error')
        return redirect(url_for('login'))

    if not session['status'] == 'Lawyer':
        flash('Please log in as lawyer to manage your schedule.', 'error')
        return redirect(url_for('login'))

    now_utc = datetime.now(timezone.utc)

    try:
        stmt = select(TimeSlot).where(
            TimeSlot.lawyer_id == lawyer_id,
            TimeSlot.slot_datetime > now_utc
        ).order_by(TimeSlot.slot_datetime)

        future_slots = db.session.scalars(stmt).all()

    except Exception as e:

        flash('Could not retrieve schedule data due to a server error.', 'danger')
        future_slots = []

    slots_by_day = {}
    for slot in future_slots:
        date_key_raw = slot.slot_datetime.strftime('%Y-%m-%d')

        if date_key_raw not in slots_by_day:
            slots_by_day[date_key_raw] = {
                'formatted_date': slot.slot_datetime.strftime('%B %d, %Y'),
                'slots': []
            }
        slots_by_day[date_key_raw]['slots'].append(slot)

    return render_template('manage_slots.html', slots_by_day=slots_by_day)


@app.route('/lawyer/slots/update_status', methods=['POST'])
@login_required
def update_slot_status():
    lawyer_id = session.get('user_id')

    if not session['status'] == 'Lawyer':
        flash('Please log in as lawyer to manage your schedule.', 'error')
        return redirect(url_for('login'))

    if not lawyer_id:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    slot_id = request.json.get('slot_id')
    new_status = request.json.get('new_status')

    # 1. Валидация входных данных
    if not slot_id or new_status not in ['available', 'unavailable']:
        return jsonify({'success': False, 'message': 'Invalid input data.'}), 400

    slot = db.session.get(TimeSlot, slot_id)

    # 2. Валидация доступа
    if not slot or slot.lawyer_id != lawyer_id:
        return jsonify({'success': False, 'message': 'Slot not found or access denied.'}), 403

    # 3. Валидация статуса
    if slot.status == 'booked':
        return jsonify({'success': False, 'message': 'Booked slots cannot be changed.'}), 400

    # 4. Обновление БД
    try:
        slot.status = new_status
        db.session.commit()
        return jsonify({'success': True, 'new_status': slot.status}), 200

    except Exception as e:
        db.session.rollback()
        # app.logger.error(f"DB commit error updating slot {slot_id}: {e}")
        return jsonify({'success': False, 'message': 'A server error occurred during update.'}), 500



@app.route('/admin-panel')
def simple_admin_dashboard():
    # 1. СТРОГАЯ ПРОВЕРКА СТАТУСА В СЕССИИ
    if session.get('status') != 'Admin':
        flash('Доступ запрещен. Войдите как администратор.', 'danger')
        return redirect(url_for('login')) # Или на любую другую страницу

    # 2. ЕСЛИ АДМИН, ПРОДОЛЖАЕМ ЗАГРУЗКУ ДАННЫХ
    try:
        # Получаем все данные
        all_users = db.session.query(User).all()
        all_consultations = db.session.query(Consultation).all()

        # Сортируем консультации по дате (свежие сверху)
        all_consultations.sort(key=lambda c: c.date, reverse=True)

    except Exception as e:
        print(f"Error fetching admin data: {e}")
        flash('Ошибка при загрузке данных администратора.', 'danger')
        # Если данные не загрузились, перенаправляем админа на его дашборд
        return redirect(url_for('user_dashboard', user_id=session.get('user_id')))

    return render_template(
        'admin_panel.html',
        users=all_users,
        consultations=all_consultations
    )


@app.route('/api/consultations/<int:consultation_id>', methods=['DELETE'])
def delete_consultation(consultation_id):
    # 1. Проверка авторизации
    user_id = session.get('user_id')
    user_status = session.get('status')

    if not user_id:
        return jsonify({'message': 'Authorization required'}), HTTPStatus.UNAUTHORIZED

    try:
        # Загружаем консультацию и связанного клиента
        consultation = db.session.query(Consultation).filter_by(id=consultation_id).first()

        if not consultation:
            return jsonify({'message': 'Consultation not found'}), HTTPStatus.NOT_FOUND

        client = db.session.query(User).filter_by(id=consultation.client_id).first()

        # 2. Проверка прав доступа: (Клиент, Юрист, или Администратор)
        is_owner = (consultation.client_id == user_id)
        is_lawyer = (consultation.lawyer_user_id == user_id)
        is_admin = (user_status == 'Admin')

        if not (is_owner or is_lawyer or is_admin):
            return jsonify(
                {'message': 'Permission denied. Only owner, lawyer, or admin can cancel.'}), HTTPStatus.FORBIDDEN

        # 3. Проверка и логика отмены

        if consultation.status == 'cancelled':
            return jsonify({'message': 'Consultation is already cancelled'}), HTTPStatus.OK

        refund_amount = Decimal(0)  # Инициализация как Decimal(0)

        # Процесс Возврата: Если консультация была оплачена, возвращаем средства.
        if consultation.payment_status == 'paid' and client:
            # ИСПРАВЛЕНИЕ: Преобразуем цену консультации в Decimal, чтобы избежать TypeError
            # Используем Decimal(str()) для надежной конвертации из float/string в Decimal
            refund_amount = Decimal(str(consultation.price))

            client.balance += refund_amount  # Теперь это Decimal += Decimal
            consultation.payment_status = 'refunded'  # Меняем статус оплаты
            print(f"Refund processed: {refund_amount} added to client {client.id} balance.")

        # Обновляем статус консультации
        consultation.status = 'cancelled'

        # Освобождаем слот
        if consultation.time_slot:
            consultation.time_slot.status = 'available'
            consultation.time_slot_id = None

        db.session.commit()

        # 4. Ответ
        return jsonify({
            'message': 'Consultation successfully cancelled.',
            'refund_details': {
                # ВОЗВРАЩАЕМ КАК СТРОКУ, Т.К. JSON НЕ СЕРИАЛИЗУЕТ DECIMAL НАПРЯМУЮ
                'amount': str(refund_amount),
                'is_refunded': refund_amount > Decimal(0)
            },
            'new_status': 'cancelled'
        }), HTTPStatus.OK

    except Exception as e:
        db.session.rollback()
        print(f"Error during consultation cancellation: {e}")
        return jsonify({'message': 'Internal server error', 'details': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


with app.app_context():
    db.create_all()
    print("DB check: db.create_all() executed.")

if __name__ == '__main__':
    app.run(debug=True)