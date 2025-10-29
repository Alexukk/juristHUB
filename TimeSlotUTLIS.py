from datetime import datetime, timedelta, time
from config import db
from models import TimeSlot, User

# Константы расписания
WORK_HOURS = list(range(9, 18))  # 9:00–17:00
LUNCH_BREAK = [13]               # 13:00–14:00
WEEKENDS = [5, 6]                # Суббота, воскресенье

def generate_time_slots_for_date_range(lawyer, start_date, end_date):
    slots = []
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() not in WEEKENDS:
            for hour in WORK_HOURS:
                if hour in LUNCH_BREAK:
                    status = 'break'
                else:
                    status = 'available'
                slot_time = datetime.combine(current_date, time(hour, 0))
                exists = TimeSlot.query.filter_by(lawyer_id=lawyer.id, slot_datetime=slot_time).first()
                if not exists:
                    slot = TimeSlot(
                        lawyer_id=lawyer.id,
                        slot_datetime=slot_time,
                        status=status
                    )
                    slots.append(slot)
        current_date += timedelta(days=1)
    db.session.add_all(slots)
    db.session.commit()


def generate_missing_slots_for_today():
    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    lawyers = User.query.filter_by(status='Lawyer').all()
    for lawyer in lawyers:
        latest_slot = TimeSlot.query.filter_by(lawyer_id=lawyer.id)\
            .order_by(TimeSlot.slot_datetime.desc()).first()
        if not latest_slot or latest_slot.slot_datetime.date() < tomorrow:
            generate_time_slots_for_date_range(lawyer, tomorrow, tomorrow)