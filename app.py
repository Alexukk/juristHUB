from flask import Flask, redirect, render_template, request, session, url_for, flash, jsonify
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from config import app, db
from models import User, Consultation
from sqlalchemy import select
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import cast, Numeric, distinct
from models import User, Review, Consultation
from sqlalchemy import func, case, text
import stripe
from datetime import date
from decimal import Decimal
from telebot import TeleBot

load_dotenv()
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
            flash('Request sent, we will answer as soon as possible!')
            return render_template('support_page.html')
        except Exception as e:
            print(e)
            flash("We have troubles sending your data try again later.")
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

        if user.status == 'Admin':
            return redirect(url_for('admin_panel'))
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


@app.route('/dashboard/<int:user_id>')
@login_required
def user_dashboard(user_id):
    # Проверка, что пользователь просматривает свой дашборд
    if session['user_id'] != user_id and session['status'] != 'Admin':
        flash('You are not authorized to view this dashboard.', 'danger')
        return redirect(url_for('index'))

    client_consultations = Consultation.query.filter_by(client_id=user_id).all()

    upcoming_meetings = [
        c.to_dict(include_lawyer=True) for c in client_consultations
        if c.status not in ['completed', 'cancelled']
    ]

    # 2. Завершенные
    completed_meetings = [
        c.to_dict(include_lawyer=True) for c in client_consultations
        if c.status == 'completed'
    ]

    cancelled_meetings = [
        c.to_dict(include_lawyer=True) for c in client_consultations
        if c.status == 'cancelled'
    ]


    return render_template(
        'user_dashboard.html',
        upcoming_meetings=upcoming_meetings,
        completed_meetings=completed_meetings,
        cancelled_meetings=cancelled_meetings,  # <--- ПЕРЕДАЕМ НОВЫЙ СПИСОК
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

        try:
            price_usd = float(lawyer.price)
            consultation_price_cents = int(price_usd * 100)

            booking_datetime = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M').replace(
                tzinfo=timezone.utc)

        except (ValueError, TypeError) as e:
            return f"Invalid data (price or datetime): {e}", 500

        # --- НОВАЯ ЛОГИКА КОПИРОВАНИЯ ССЫЛКИ/АДРЕСА ---
        meeting_url = None
        location_gmaps = None

        if consultation_type == 'Online':
            meeting_url = lawyer.zoom_link  # Используем zoom_link, если это у вас есть
        elif consultation_type == 'Offline':
            location_gmaps = lawyer.office_address
        # ---------------------------------------------------

        new_consultation = Consultation(
            client_id=client_id,
            lawyer_user_id=lawyer_id,
            date=booking_datetime,
            type=consultation_type,
            status='pending',
            payment_status='unpaid',

            # --- ПЕРЕДАЕМ СКОПИРОВАННЫЕ ЗНАЧЕНИЯ ---
            meeting_url=meeting_url,
            location_gmaps=location_gmaps,
            price=price_usd
            # ----------------------------------------
        )
        db.session.add(new_consultation)
        db.session.commit()
        print(meeting_url)
        print(location_gmaps)

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
            metadata={'consultation_id': new_consultation.id},

            success_url=url_for('payment_success', _external=True) + '?consultation_id=' + str(new_consultation.id),
            cancel_url=url_for('payment_canceled', _external=True) + '?consultation_id=' + str(new_consultation.id),
        )

        return redirect(stripe_session.url)

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
    consultation = db.session.get(Consultation, consultation_id)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'cancel':

            if consultation.payment_status == 'paid':

                # 1. Возврат средств клиенту
                client = db.session.get(User, consultation.client_id)
                refund_amount = Decimal(str(consultation.price))

                if client:
                    client.balance += refund_amount

                    if session.get('user_id') == client.id:
                        session['balance'] = float(client.balance)

                    flash(f'Consultation cancelled. ${refund_amount:.2f} refunded to your balance.', 'success')
                    consultation.payment_status = 'refunded'
                else:
                    consultation.payment_status = 'refund_pending_manual'
                    flash(
                        f'Consultation cancelled, but user (ID: {consultation.client_id}) record is missing. Refund required manual check.',
                        'danger')

                # 2. Снятие комиссии с баланса юриста
                lawyer = db.session.get(User, consultation.lawyer_user_id)

                if lawyer:
                    full_price = Decimal(str(consultation.price))
                    # Расчет суммы, которую нужно снять (заработок юриста)
                    earnings_to_reverse = full_price * (Decimal('1.00') - PLATFORM_COMMISSION_RATE)

                    lawyer.balance -= earnings_to_reverse

                    # Логика для предотвращения отрицательного баланса
                    if lawyer.balance < 0:
                        lawyer.balance = Decimal('0.00')
                        flash(f'Warning: Lawyer {lawyer.fullname} had insufficient balance to cover the refund.',
                              'warning')

            elif consultation.payment_status == 'unpaid':
                flash('Consultation cancelled successfully. No refund necessary as payment was pending.', 'success')
                # Здесь не нужно трогать баланс юриста или клиента

            # 3. Обновление статуса консультации и сохранение
            consultation.status = 'cancelled'
            db.session.commit()

            return redirect(url_for('user_dashboard', user_id=session['user_id']))

    if not consultation:
        flash('Consultation not found.', 'danger')
        return redirect(url_for('user_dashboard', user_id=session['user_id']))

    is_client = consultation.client_id == session['user_id']
    is_lawyer = consultation.lawyer_user_id == session['user_id']

    if not (is_client or is_lawyer or session['status'] == 'Admin'):
        flash('You do not have access to this consultation.', 'danger')
        return redirect(url_for('my_consultations'))

    consultation_data = consultation.to_dict()
    consultation_data['js_date_iso'] = consultation.date.isoformat()
    lawyer_name = db.session.get(User, consultation.lawyer_user_id).fullname

    return render_template(
        'consultation_details.html',
        consultation=consultation_data,
        lawyer_name=lawyer_name,
        is_client=is_client,
    )


with app.app_context():
    db.create_all()
    print("DB check: db.create_all() executed.")

if __name__ == '__main__':
    app.run(debug=True)