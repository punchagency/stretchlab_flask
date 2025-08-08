from datetime import datetime, timedelta


def get_start_and_end_date(duration, start_date_str=None, end_date_str=None):
    if duration == "mtd":
        current_date = datetime.now()
        start_date = current_date.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_date = (current_date).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    elif duration == "ytd":
        current_date = datetime.now()
        start_date = current_date.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_date = (current_date).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    elif duration == "last_30_days":
        current_date = datetime.now()
        end_date = (current_date).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        start_date = (end_date - timedelta(days=30)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif duration == "last_7_days":
        current_date = datetime.now()

        # INFO - Exclude today: end_date is yesterday (end of day), start_date is 6 days before yesterday (start of day)
        end_date = (current_date).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        start_date = (end_date - timedelta(days=6)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    elif duration == "last_90_days":
        current_date = datetime.now()
        end_date = (current_date).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        start_date = (end_date - timedelta(days=90)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif duration == "custom":

        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

    return start_date, end_date
