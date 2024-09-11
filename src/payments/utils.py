import datetime


async def payment_week(created_at):
    current_date = datetime.datetime.now()
    current_week = (current_date - created_at).days // 7

    ws = created_at + datetime.timedelta(days=current_week * 7)
    we = ws + datetime.timedelta(days=7)

    return ws, we, current_week


def get_current_week_dates():
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def get_previous_week_dates():
    today = datetime.date.today()
    previous_monday = today - datetime.timedelta(days=today.weekday() + 7)
    previous_sunday = previous_monday + datetime.timedelta(days=6)
    return previous_monday, previous_sunday
