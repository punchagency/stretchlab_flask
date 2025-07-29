from datetime import datetime, timedelta
from calendar import monthrange


def get_start_and_end_date(duration):
    start_date = None
    end_date = None

    if duration == "this_year":
        start_date = datetime.now().replace(day=1, month=1, year=datetime.now().year)
        end_date = datetime.now().replace(
            day=31, month=12, year=datetime.now().year
        ) + timedelta(days=1)
    elif duration == "this_month":
        current_date = datetime.now()
        start_date = current_date.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        _, last_day_of_month = monthrange(current_date.year, current_date.month)

        end_date = current_date.replace(
            day=last_day_of_month, hour=23, minute=59, second=59, microsecond=999999
        ) + timedelta(days=1)
    elif duration == "last_month":
        current_date = datetime.now()
        first_day_this_month = current_date.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        last_day_last_month = first_day_this_month - timedelta(days=1)
        start_date = last_day_last_month.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_date = last_day_last_month.replace(
            hour=23, minute=59, second=59, microsecond=999999
        ) + timedelta(days=1)
    elif duration == "last_30_days":
        current_date = datetime.now()
        end_date = (current_date - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        ) + timedelta(days=1)
        start_date = (end_date - timedelta(days=29)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif duration == "last_7_days":
        current_date = datetime.now()

        # INFO - Exclude today: end_date is yesterday (end of day), start_date is 6 days before yesterday (start of day)
        yesterday = (current_date - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        start_date = (yesterday - timedelta(days=6)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date = yesterday + timedelta(days=1)
    # elif duration == "yesterday":
    #     current_date = datetime.now()

    #     start_date = (current_date - timedelta(days=1)).replace(
    #         hour=0, minute=0, second=0, microsecond=0
    #     )
    #     end_date = (current_date - timedelta(days=1)).replace(
    #         hour=23, minute=59, second=59, microsecond=999999
    #     )
    elif duration == "yesterday":
        current_date = datetime.now()

        start_date = (current_date).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = (current_date).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

    return start_date, end_date


def handle_total_visits(duration, total_visits, start_date=None, end_date=None):
    if duration == "this_year":
        monthly_data = []
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        # all_bookings = []
        # for visit_data in total_visits:
        #     if visit_data:
        #         all_bookings.extend(visit_data)
        monthly_counts = {}
        for booking in total_visits:
            sanitized_date = booking["appointment_date"].replace(",", "")
            booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
            booking_date = booking_date.replace(year=start_date.year)
            month = booking_date.month
            if month not in monthly_counts:
                monthly_counts[month] = 0
            monthly_counts[month] += 1

        for month in range(1, 13):
            monthly_data.append(
                {
                    "label": month_names[month - 1],
                    "value": monthly_counts.get(month, 0),
                    "total": len(total_visits),
                }
            )

        return {"data": monthly_data}
    elif duration in ["this_month", "last_month", "last_30_days"]:

        daily_data = []
        day_start = start_date

        while day_start <= end_date:
            day_end = day_start.replace(
                hour=23, minute=59, second=59, microsecond=999999
            )

            count = 0
            for booking in total_visits:
                sanitized_date = booking["appointment_date"].replace(",", "")
                booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
                booking_date = booking_date.replace(year=day_start.year)
                if day_start <= booking_date <= day_end:
                    count += 1

            day_str = str(day_start.day).lstrip("0")
            label = f"{day_start.strftime('%b')} {day_str}"
            daily_data.append({"label": label, "value": count})

            day_start = day_end + timedelta(microseconds=1)

        return {"data": daily_data[:-1]}
    elif duration == "last_7_days":
        daily_data = []
        days = [start_date + timedelta(days=i) for i in range(7)]
        daily_counts = {d.strftime("%a"): 0 for d in days}

        for booking in total_visits:
            sanitized_date = booking["appointment_date"].replace(",", "")
            booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
            booking_date = booking_date.replace(year=start_date.year)
            for d in days:
                if d.date() == booking_date.date():
                    day_label = d.strftime("%a")
                    daily_counts[day_label] += 1
                    break

        for d in days:
            daily_data.append(
                {
                    "label": d.strftime("%a"),
                    "value": daily_counts[d.strftime("%a")],
                    "total": len(total_visits),
                }
            )

        return {"data": daily_data}
    elif duration == "yesterday" or duration == "today":
        hour_labels = [
            f"{h} AM" if h < 12 else (f"12 PM" if h == 12 else f"{h-12} PM")
            for h in range(6, 22)
        ]
        hour_buckets = {h: 0 for h in range(6, 22)}

        for booking in total_visits:
            booking_time_str = booking.get("appointment_date")
            if not booking_time_str:
                continue
            try:
                time_str = booking_time_str.replace(",", "")
                time_obj = datetime.strptime(time_str, "%A %B %d %I:%M %p")
                time_obj = time_obj.replace(year=start_date.year)

                hour = time_obj.hour
                if 6 <= hour <= 21:
                    hour_buckets[hour] += 1
            except Exception:
                continue

        hourly_data = []
        for idx, h in enumerate(range(6, 22)):
            hourly_data.append(
                {
                    "label": hour_labels[idx],
                    "value": hour_buckets[h],
                    "total": len(total_visits),
                }
            )

        return {"data": hourly_data}


def handle_percentage_of_submitted_bookings(
    duration, all_bookings, submitted_by_app, start_date=None, end_date=None
):
    if duration == "this_year":
        monthly_data = []
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        monthly_total_counts = {}
        monthly_submitted_counts = {}

        for booking in all_bookings:
            sanitized_date = booking["appointment_date"].replace(",", "")
            date_obj = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
            booking_date = date_obj.replace(year=start_date.year)
            month = booking_date.month
            if month not in monthly_total_counts:
                monthly_total_counts[month] = 0
            monthly_total_counts[month] += 1
        for booking in submitted_by_app:
            booking_date = datetime.strptime(booking["created_at"][:10], "%Y-%m-%d")
            month = booking_date.month
            if month not in monthly_submitted_counts:
                monthly_submitted_counts[month] = 0
            monthly_submitted_counts[month] += 1

        for month in range(1, 13):
            total_bookings = monthly_total_counts.get(month, 0)
            submitted_bookings = monthly_submitted_counts.get(month, 0)

            percentage = 0
            if total_bookings > 0:
                percentage = (submitted_bookings / total_bookings) * 100

            monthly_data.append(
                {
                    "label": month_names[month - 1],
                    "value": round(percentage, 2),
                    "total": total_bookings,
                }
            )
        return {"data": monthly_data}

    elif duration in ["this_month", "last_month", "last_30_days"]:
        daily_data = []
        range_start = start_date.date()
        range_end = end_date.date()
        current_day = range_start
        # print(submitted_by_app, "submitted_by_app")
        while current_day <= range_end:
            total_count = 0
            submitted_count = 0
            for booking in all_bookings:
                sanitized_date = booking["appointment_date"].replace(",", "")
                date_obj = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
                date_obj = date_obj.replace(year=current_day.year)
                booking_date = date_obj.date()
                if booking_date == current_day:
                    total_count += 1
            for booking in submitted_by_app:
                booking_date = datetime.strptime(
                    booking["created_at"][:10], "%Y-%m-%d"
                ).date()

                if booking_date == current_day:
                    submitted_count += 1
            percentage = (submitted_count / total_count * 100) if total_count > 0 else 0
            day_str = str(current_day.day).lstrip("0")
            label = f"{current_day.strftime('%b')} {day_str}"
            daily_data.append(
                {"label": label, "value": round(percentage, 2), "total": total_count}
            )
            current_day += timedelta(days=1)

        return {"data": daily_data[:-1]}

    elif duration == "last_7_days":
        daily_data = []
        days = [start_date + timedelta(days=i) for i in range(7)]
        daily_total_counts = {d.strftime("%a"): 0 for d in days}
        daily_submitted_counts = {d.strftime("%a"): 0 for d in days}

        for booking in all_bookings:
            sanitized_date = booking["appointment_date"].replace(",", "")
            date_obj = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
            date_obj = date_obj.replace(year=start_date.year)
            booking_date = date_obj
            for d in days:
                if d.date() == booking_date.date():
                    day_label = d.strftime("%a")
                    daily_total_counts[day_label] += 1
                    break

        for booking in submitted_by_app:
            booking_date = datetime.strptime(booking["created_at"][:10], "%Y-%m-%d")
            for d in days:
                if d.date() == booking_date.date():
                    day_label = d.strftime("%a")
                    daily_submitted_counts[day_label] += 1
                    break

        for d in days:
            day_label = d.strftime("%a")
            total = daily_total_counts[day_label]
            submitted = daily_submitted_counts[day_label]
            percentage = (submitted / total * 100) if total > 0 else 0
            daily_data.append(
                {"label": day_label, "value": round(percentage, 2), "total": total}
            )

        return {"data": daily_data}
    elif duration == "yesterday" or duration == "today":
        hour_labels = [
            f"{h} AM" if h < 12 else (f"12 PM" if h == 12 else f"{h-12} PM")
            for h in range(6, 22)
        ]
        hour_total_counts = {h: 0 for h in range(6, 22)}
        hour_submitted_counts = {h: 0 for h in range(6, 22)}

        for booking in all_bookings:
            booking_time_str = booking.get("appointment_date")
            if not booking_time_str:
                continue
            try:
                time_str = booking_time_str.replace(",", "")
                time_obj = datetime.strptime(time_str, "%A %B %d %I:%M %p")
                time_obj = time_obj.replace(year=start_date.year)
                hour = time_obj.hour
                if 6 <= hour <= 21:
                    hour_total_counts[hour] += 1
            except Exception:
                continue

        for booking in submitted_by_app:
            booking_time_str = booking.get("appointment_date")
            if not booking_time_str:
                continue
            try:
                time_str = booking_time_str.replace(",", "")
                time_obj = datetime.strptime(time_str, "%A %B %d %I:%M %p")
                time_obj = time_obj.replace(year=start_date.year)
                hour = time_obj.hour
                if 6 <= hour <= 21:
                    hour_submitted_counts[hour] += 1
            except Exception:
                continue

        hourly_data = []
        for idx, h in enumerate(range(6, 22)):
            total = hour_total_counts[h]
            submitted = hour_submitted_counts[h]
            percentage = (submitted / total * 100) if total > 0 else 0
            hourly_data.append(
                {
                    "label": hour_labels[idx],
                    "value": round(percentage, 2),
                    "total": total,
                }
            )

        return {"data": hourly_data}


def handle_avg_visit_quality_percentage(
    duration, all_bookings, start_date=None, end_date=None
):
    if duration == "this_year":

        monthly_data = []
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        monthly_percentages = {}
        monthly_counts = {}

        for booking in all_bookings:
            sanitized_date = booking["appointment_date"].replace(",", "")
            booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
            booking_date = booking_date.replace(year=start_date.year)
            month = booking_date.month
            if month not in monthly_percentages:
                monthly_percentages[month] = []
            monthly_percentages[month].append(booking["percentage"])

        for month in range(1, 13):
            percentages = monthly_percentages.get(month, [])
            avg_percentage = sum(percentages) / len(percentages) if percentages else 0
            monthly_data.append(
                {
                    "label": month_names[month - 1],
                    "value": round(avg_percentage, 2),
                }
            )

        return {"data": monthly_data}
    elif duration in ["this_month", "last_month", "last_30_days"]:
        daily_data = []
        day_labels = []
        daily_percentages = {}

        num_days = (end_date - start_date).days + 1
        for i in range(num_days):
            day = start_date + timedelta(days=i)
            label = day.strftime("%b %d")
            day_labels.append(label)
            daily_percentages[label] = []

        for booking in all_bookings:
            try:
                sanitized_date = booking["appointment_date"].replace(",", "")
                booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
                booking_date = booking_date.replace(year=start_date.year)
                label = booking_date.strftime("%b %d")
                if label in daily_percentages:
                    percentage = float(booking.get("percentage", 0))
                    daily_percentages[label].append(percentage)
            except (ValueError, TypeError):
                continue

        for label in day_labels:
            percentages = daily_percentages.get(label, [])
            avg_percentage = sum(percentages) / len(percentages) if percentages else 0
            daily_data.append(
                {
                    "label": label,
                    "value": round(avg_percentage, 2),
                    "total": len(all_bookings),
                }
            )

        return {"data": daily_data[:-1]}
    elif duration == "last_7_days":
        daily_data = []
        days = [start_date + timedelta(days=i) for i in range(7)]
        daily_percentages = {d.strftime("%a"): [] for d in days}

        for booking in all_bookings:
            sanitized_date = booking["appointment_date"].replace(",", "")
            booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
            booking_date = booking_date.replace(year=start_date.year)
            for d in days:
                if d.date() == booking_date.date():
                    day_label = d.strftime("%a")
                    daily_percentages[day_label].append(booking["percentage"])
                    break

        for d in days:
            day_label = d.strftime("%a")
            percentages = daily_percentages[day_label]
            avg_percentage = sum(percentages) / len(percentages) if percentages else 0
            daily_data.append(
                {
                    "label": day_label,
                    "value": round(avg_percentage, 2),
                    "total": len(all_bookings),
                }
            )

        return {"data": daily_data}
    elif duration == "yesterday" or duration == "today":
        daily_data = []
        hour_labels = [
            f"{h} AM" if h < 12 else (f"12 PM" if h == 12 else f"{h-12} PM")
            for h in range(6, 22)
        ]
        hour_buckets = {h: [] for h in range(6, 22)}

        for booking in all_bookings:
            booking_time_str = booking.get("appointment_date").replace(",", "")
            if not booking_time_str:
                continue
            try:
                time_obj = datetime.strptime(booking_time_str, "%A %B %d %I:%M %p")
                time_obj = time_obj.replace(year=start_date.year)
                hour = time_obj.hour
                if 6 <= hour <= 21:
                    hour_buckets[hour].append(booking["percentage"])
            except Exception:
                continue

        for idx, h in enumerate(range(6, 22)):
            percentages = hour_buckets[h]

            avg_percentage = sum(percentages) / len(percentages) if percentages else 0
            daily_data.append(
                {
                    "label": hour_labels[idx],
                    "value": round(avg_percentage, 2),
                    "total": len(all_bookings),
                }
            )

        return {"data": daily_data}


def handle_avg_aggregate_note_quality_percentage(
    duration, all_bookings, start_date=None, end_date=None
):
    if duration == "this_year":
        monthly_data = []
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        monthly_percentages = {}
        monthly_counts = {}

        for booking in all_bookings:
            sanitized_date = booking["appointment_date"].replace(",", "")
            booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
            booking_date = booking_date.replace(year=start_date.year)
            month = booking_date.month
            if month not in monthly_percentages:
                monthly_percentages[month] = []
            monthly_percentages[month].append(booking["percentage"])

        for month in range(1, 13):
            percentages = monthly_percentages.get(month, [])
            avg_percentage = sum(percentages) / len(percentages) if percentages else 0
            monthly_data.append(
                {
                    "label": month_names[month - 1],
                    "value": round(avg_percentage, 2),
                    "total": len(all_bookings),
                }
            )

        return {"data": monthly_data}
    elif duration in ["this_month", "last_month", "last_30_days"]:
        print("duration", duration)
        print("start_date", start_date)
        print("end_date", end_date)
        daily_data = []
        day_labels = []
        daily_percentages = {}

        num_days = (end_date - start_date).days + 1
        for i in range(num_days):
            day = start_date + timedelta(days=i)
            label = day.strftime("%b %d")
            day_labels.append(label)
            daily_percentages[label] = []

        for booking in all_bookings:
            try:
                sanitized_date = booking["appointment_date"].replace(",", "")
                booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
                booking_date = booking_date.replace(year=start_date.year)
                label = booking_date.strftime("%b %d")
                if label in daily_percentages:
                    percentage = float(booking.get("percentage", 0))
                    daily_percentages[label].append(percentage)
            except (ValueError, TypeError):
                continue

        for label in day_labels:
            percentages = daily_percentages.get(label, [])
            avg_percentage = sum(percentages) / len(percentages) if percentages else 0
            daily_data.append(
                {
                    "label": label,
                    "value": round(avg_percentage, 2),
                    "total": len(all_bookings),
                }
            )

        return {"data": daily_data[:-1]}
    elif duration == "last_7_days":
        daily_data = []
        days = [start_date + timedelta(days=i) for i in range(7)]
        daily_percentages = {d.strftime("%a"): [] for d in days}

        for booking in all_bookings:
            sanitized_date = booking["appointment_date"].replace(",", "")
            booking_date = datetime.strptime(sanitized_date, "%A %B %d %I:%M %p")
            booking_date = booking_date.replace(year=start_date.year)
            for d in days:
                if d.date() == booking_date.date():
                    day_label = d.strftime("%a")
                    daily_percentages[day_label].append(booking["percentage"])
                    break

        for d in days:
            day_label = d.strftime("%a")
            percentages = daily_percentages[day_label]
            avg_percentage = sum(percentages) / len(percentages) if percentages else 0
            daily_data.append(
                {
                    "label": day_label,
                    "value": round(avg_percentage, 2),
                    "total": len(all_bookings),
                }
            )

        return {"data": daily_data}
    elif duration == "yesterday" or duration == "today":
        daily_data = []
        hour_labels = [
            f"{h} AM" if h < 12 else (f"12 PM" if h == 12 else f"{h-12} PM")
            for h in range(6, 22)
        ]
        hour_buckets = {h: [] for h in range(6, 22)}

        for booking in all_bookings:
            booking_time_str = booking.get("appointment_date").replace(",", "")
            if not booking_time_str:
                continue
            try:
                time_obj = datetime.strptime(booking_time_str, "%A %B %d %I:%M %p")
                time_obj = time_obj.replace(year=start_date.year)
                hour = time_obj.hour
                if 6 <= hour <= 21:
                    hour_buckets[hour].append(booking["percentage"])
            except Exception:
                continue

        for idx, h in enumerate(range(6, 22)):
            percentages = hour_buckets[h]
            avg_percentage = sum(percentages) / len(percentages) if percentages else 0
            daily_data.append(
                {
                    "label": hour_labels[idx],
                    "value": round(avg_percentage, 2),
                    "total": len(all_bookings),
                }
            )

        return {"data": daily_data}
