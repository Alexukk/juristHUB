from flask import Flask, redirect, render_template, request, session, url_for, flash, jsonify
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from config import app, db
from models import User, Consultation
from sqlalchemy import select
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import cast, Numeric, distinct
from models import User, Review, Consultation # Убедитесь, что импортировали Review
from sqlalchemy import func, case, text # Добавьте импорты func и case
import stripe
from datetime import date


load_dotenv()

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

    try:
        query = (
            db.select(Review)
            .options(
                db.joinedload(Review.client),
                db.joinedload(Review.lawyer)
            )
            .order_by(Review.date.desc())
        )


        reviews_objects = db.session.execute(query).scalars().all()

        reviews_list = [
            review.to_dict() for review in reviews_objects
        ]

        print(f"✅ Loaded {len(reviews_list)} reviews from the database.")

        return render_template('reviews.html', reviews=reviews_list)

    except Exception as e:
        print(f"❌ ERROR loading reviews from DB: {e}")
        return render_template('reviews.html', reviews=[])


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

        if user.status == 'Admin':
            return redirect(url_for('admin_panel'))
        return redirect(f"/user/dashboard/{user.id}")

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

        return redirect(f"/user/dashboard/{new_user.id}")


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
            booking_endpoint=url_for('book_consultation', lawyer_id=lawyer_data['id']),
            today_date=today_date_str
        )

    except Exception as e:
        print(f"❌ CRITICAL ERROR accessing lawyer profile: {e}")
        return "Internal Server Error", 500


@app.route('/book-consultation/<int:lawyer_id>')
@login_required
def book_consultation(lawyer_id):


    return redirect('/')


@app.route('/user/dashboard/<int:user_id>')
@login_required
def user_dashboard(user_id):
    if session.get('user_id') != user_id:
        flash('Access denied. You can only view your own profile.', 'danger')
        return redirect(url_for('index'))

    upcoming_meetings = [
        {
            'lawyer_name': 'Dr. Alan Smith (Tax Law)',
            'date': '2025-11-05',
            'time': '14:00',
            'is_paid': True,
            'id': 101
        },
        {
            'lawyer_name': 'Ms. Jane Doe (Family Law)',
            'date': '2025-10-30',
            'time': '10:30',
            'is_paid': False,
            'id': 102
        }
    ]

    completed_meetings = [
        {
            'lawyer_name': 'Mr. Bob Johnson (Real Estate)',
            'date': '2025-09-15',
            'time': '11:00',
            'id': 95
        }
    ]

    return render_template(
        'user_dashboard.html',
        upcoming_meetings=upcoming_meetings,
        completed_meetings=completed_meetings,
    )



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
    if session['user_id'] == user_id or session['status'] == 'Admin':
        if request.method == 'GET':
            return render_template('profile-edit.html')
        else:
            username = request.form.get('username')
            email = request.form.get('email')
            try:
                user = User.query.get_or_404(session['user_id'])
                user.fullname = username
                user.email = email
                if request.form.get('password'):
                    if request.form.get('password') != request.form.get('confirm_password'):
                        flash('New password and confirmation do not match.', 'warning')
                        return redirect(url_for('edit_profile', user_id=user_id))
                    password = request.form.get('password')
                    user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                session['email'] = email
                session['username'] = username
                db.session.commit()
                flash('Your account details have been successfully updated!', 'success')
            except Exception as e:
                db.session.rollback()
                print('An error occured while changing profile info: \n', e)
                flash('An error occurred', 'danger')
    else:
        flash("You can't edit details of another user", "danger")
        return redirect(url_for('index'))


    return redirect(url_for('user_dashboard', user_id=session['user_id']))


# STRIPE PAYMENTS LOGIC

@app.route('/consultation/<int:lawyer_id>/checkout', methods=['POST', 'GET'])
@login_required
def payment_provider(lawyer_id):
    # Убираем session=session из аргументов функции, так как Flask передает ее глобально
    if request.method == 'POST':
        # ⚠️ ПОЛУЧЕНИЕ ID КЛИЕНТА
        client_id = session.get('user_id')
        if not client_id:
            # Если @login_required не сработает или сессия пуста
            return redirect(url_for('login_route'))

            # 1. Получение данных бронирования
        date_str = request.form.get('booking_date')
        time_str = request.form.get('booking_time')
        consultation_type = request.form.get('type', 'Online')

        # 2. Получение цены юриста и конвертация
        lawyer = db.session.get(User, lawyer_id)
        if not lawyer or lawyer.status != 'Lawyer':
            return "Lawyer not found or is inactive", 404

        try:
            price_usd = float(lawyer.price)
            consultation_price_cents = int(price_usd * 100)

            booking_datetime = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M').replace(
                tzinfo=timezone.utc)

        except (ValueError, TypeError) as e:
            return f"Invalid data (price or datetime): {e}", 500

        # 3. Регистрация заказа (предварительная запись в БД)
        new_consultation = Consultation(
            client_id=client_id,
            lawyer_user_id=lawyer_id,
            date=booking_datetime,
            type=consultation_type,
            status='pending',
            payment_status='unpaid'  # Ставим 'unpaid', пока Stripe не подтвердит оплату
        )
        db.session.add(new_consultation)
        db.session.commit()

        # 4. Создание сессии Stripe Checkout
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
            # !!! Передаем ID консультации через metadata для использования в Webhook !!!
            metadata={'consultation_id': new_consultation.id},

            # URL-адреса для перенаправления
            success_url=url_for('payment_success', _external=True) + '?consultation_id=' + str(new_consultation.id),
            cancel_url=url_for('payment_canceled', _external=True) + '?consultation_id=' + str(new_consultation.id),
        )

        return redirect(stripe_session.url)  # Используем stripe_session, чтобы не перезаписать Flask session

    return redirect('/')


# --- ОБРАБОТКА ВЕБХУКОВ (Webhook) ---
@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('stripe-signature')
    event = None

    # 1. Проверка подписи (Signature Verification) для безопасности
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Неверный payload
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
                    # Устанавливаем статус 'paid'
                    consultation.payment_status = 'paid'
                    consultation.status = 'pending'  # Или 'scheduled'

                    # 💡 TODO: Здесь можно сгенерировать ссылку Zoom/записать адрес в БД

                    db.session.commit()
                    # 📧 TODO: Отправить уведомления юристу и клиенту
                    print(f"WEBHOOK SUCCESS: Consultation {consultation_id} marked as PAID.")

            except Exception as db_error:
                db.session.rollback()
                # Возвращаем 500, чтобы Stripe попытался отправить событие еще раз
                return jsonify({'message': f'DB Error: {db_error}'}), 500

                # 3. Возврат успешного ответа
    # Всегда возвращаем 200 OK, чтобы Stripe знал, что событие получено
    return jsonify({'status': 'success'}), 200


# --- МАРШРУТЫ ЗАВЕРШЕНИЯ ОПЛАТЫ (UX Redirects) ---
@app.route('/consultation/payment/success')
def payment_success():
    consultation_id = request.args.get('consultation_id')
    consultation = db.session.get(Consultation, consultation_id)

    # Мы не обновляем статус здесь, а просто информируем пользователя.
    # Фактическое обновление сделает Webhook.
    if consultation:
        return f"Booking confirmed! We are now verifying your payment via Stripe. Consultation ID: {consultation_id}. Check your dashboard soon."

    return "Error: Booking not found."


@app.route('/consultation/payment/cancel')
def payment_canceled():
    consultation_id = request.args.get('consultation_id')
    consultation = db.session.get(Consultation, consultation_id)

    if consultation:
        # Удаляем бронирование, так как оплаты не было и она не ожидается
        db.session.delete(consultation)
        db.session.commit()

    return 'Payment canceled. The booking has been deleted.'


with app.app_context():
    db.create_all()
    print("DB check: db.create_all() executed.")

if __name__ == '__main__':
    app.run(debug=True)