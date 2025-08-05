from datetime import datetime, timedelta
import json
import logging
from flask import Blueprint, jsonify, request
from ..utils.middleware import require_bearer_token
from ..utils.utils import (
    decode_jwt_token,
)
from ..payment.stripe_utils import get_balance_for_month, get_subscription_details
from calendar import monthrange
from ..utils.dashboard import (
    get_start_and_end_date,
    handle_total_visits,
    handle_percentage_of_submitted_bookings,
    handle_avg_visit_quality_percentage,
    handle_avg_aggregate_note_quality_percentage,
)

routes = Blueprint("dashboard", __name__)


def get_bookings_info(token):
    try:
        user_data = decode_jwt_token(token)
        user_id = user_data["user_id"]
        bookings_info = None
        user = (
            supabase.table("businesses")
            .select("admin_id, username")
            .eq("admin_id", user_id)
            .execute()
        )
        if not user.data:
            return jsonify({"message": "Business not found", "status": "error"}), 404
        business_info = user.data[0]
        business_admin_id = business_info["admin_id"]
        business_name = business_info["username"]
        bookings_in_month = 0
        bookings_in_last_month = 0
        get_config_id = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", business_admin_id)
            .execute()
        )
        if not get_config_id.data:
            return jsonify({"message": "No config id found", "status": "error"}), 404

        first_day_this_month = datetime.now().replace(day=1)
        first_day_last_month = (first_day_this_month - timedelta(days=1)).replace(day=1)
        year = first_day_this_month.year
        month = first_day_this_month.month
        num_days = monthrange(year, month)[1]
        first_day_next_month = first_day_this_month + timedelta(days=num_days)

        offset = 0
        limit = 1000

        while True:
            bookings_in_month_records = (
                supabase.table("robot_process_automation_notes_records")
                .select("*")
                .eq("config_id", get_config_id.data[0]["id"])
                .gte("created_at", first_day_this_month.strftime("%Y-%m-%d"))
                .lt(
                    "created_at",
                    first_day_next_month.strftime("%Y-%m-%d"),
                )
                .range(offset, offset + limit - 1)
                .execute()
            )
            if bookings_in_month_records.data:
                bookings_in_month += len(bookings_in_month_records.data)
            if len(bookings_in_month_records.data) < limit:
                break
            offset += limit

        offset = 0
        limit = 1000

        while True:

            bookings_in_last_month_records = (
                supabase.table("robot_process_automation_notes_records")
                .select("*")
                .eq("config_id", get_config_id.data[0]["id"])
                .gte("created_at", first_day_last_month.strftime("%Y-%m-%d"))
                .lt("created_at", first_day_this_month.strftime("%Y-%m-%d"))
                .range(offset, offset + limit - 1)
                .execute()
            )
            if bookings_in_last_month_records.data:
                bookings_in_last_month += len(bookings_in_last_month_records.data)
            if len(bookings_in_last_month_records.data) < limit:
                break
            offset += limit

        if bookings_in_month == 0 and bookings_in_last_month == 0:
            aggregation = 0

        elif bookings_in_last_month == 0:
            aggregation = ((bookings_in_month - bookings_in_last_month) / 1) * 100

        else:
            aggregation = (
                (bookings_in_month - bookings_in_last_month)
                / bookings_in_last_month
                * 100
            )

        bookings_info = {
            "bookings_in_month": bookings_in_month,
            "bookings_in_last_month": bookings_in_last_month,
            "business_name": business_name,
            "aggregation": aggregation,
            "upwards_trend": aggregation > 0,
            "neutral_trend": aggregation == 0,
        }

        return bookings_info
    except Exception as e:
        logging.error(f"Error in get_bookings_info: {str(e)}")
        return e


@routes.route("/first_row", methods=["GET"])
@require_bearer_token
def get_first_row(token):
    try:
        bookings_info = get_bookings_info(token)
        balance_info = get_balance_for_month()
        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "bookings_info": bookings_info,
                        "balance_info": balance_info,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/first_row: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get_chart_filters", methods=["GET"])
@require_bearer_token
def get_chart_filters(token):
    try:
        user_data = decode_jwt_token(token)
        user_id = user_data["user_id"]
        filter_by = request.args.get("filter_by", None)
        get_config_id = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", user_id)
            .execute()
        )
        if not get_config_id.data:
            return jsonify({"error": "No config id found", "status": "error"}), 400

        flexologists = (
            supabase.table("robot_process_automation_notes_records")
            .select("flexologist_name")
            .eq("config_id", get_config_id.data[0]["id"])
            .execute()
        )
        if flexologists.data:
            flexologists = sorted(
                set(
                    flexologist["flexologist_name"] for flexologist in flexologists.data
                )
            )
        else:
            flexologists = []

        business_info = (
            supabase.table("businesses")
            .select(" note_taking_subscription_id")
            .eq("admin_id", user_id)
            .execute()
        )

        locations = (
            supabase.table("robot_process_automation_config")
            .select("selected_locations")
            .eq("admin_id", user_id)
            .execute()
        )
        if not filter_by:
            filters = [
                {
                    "label": "Total Client Visits",
                    "value": "total_client_visits",
                },
                {
                    "label": "Avg 1st Visit Quality %",
                    "value": "avg_1st_visit_quality_percentage",
                },
                {
                    "label": "Avg Subsequent Visit Quality %",
                    "value": "avg_subsequent_visit_quality_percentage",
                },
                {
                    "label": "Avg Aggregate Note Quality %",
                    "value": "avg_aggregate_note_quality_percentage",
                },
            ]
        else:
            filters = [
                {
                    "label": "Total Client Visits",
                    "value": "total_client_visits",
                },
                {
                    "label": "Avg. Note Quality %",
                    "value": "note_quality_percentage",
                },
            ]

        if business_info.data[0]["note_taking_subscription_id"]:
            filters = [
                {
                    "label": "% App Submissions",
                    "value": "percentage_app_submission",
                },
            ] + filters

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "flexologists": list(flexologists),
                        "locations": (
                            json.loads(locations.data[0]["selected_locations"])
                            if locations.data[0]["selected_locations"]
                            else []
                        ),
                        "filters": filters,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/get_chart_filters: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/second_row", methods=["GET"])
@require_bearer_token
def get_second_row(token):
    try:
        user_data = decode_jwt_token(token)
        user_id = user_data["user_id"]
        duration = request.args.get("duration", "this_year")
        location = request.args.get("location", None)
        flexologist = request.args.get("flexologist", None)
        dataset = request.args.get("dataset", "total_client_visits")

        if not location and not flexologist:
            return (
                jsonify(
                    {
                        "error": "Location or flexologist are required",
                        "status": "error",
                    }
                ),
                400,
            )

        if duration == "custom":
            start_date_str = request.args.get("start_date")
            end_date_str = request.args.get("end_date")
            if not start_date_str or not end_date_str:
                return (
                    jsonify(
                        {"error": "Start and end date are required", "status": "error"}
                    ),
                    400,
                )
            start_date, end_date = get_start_and_end_date(
                duration, start_date_str, end_date_str
            )

        else:
            start_date, end_date = get_start_and_end_date(duration)

        if not start_date or not end_date:
            return (
                jsonify({"error": "Invalid duration", "status": "error"}),
                400,
            )

        get_config_id = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", user_id)
            .execute()
        )
        if not get_config_id.data:
            return jsonify({"error": "No config id found", "status": "error"}), 400
        print(start_date, end_date, "start_date, end_date")
        if dataset == "total_client_visits":
            total_visits = []
            offset = 0
            limit = 1000

            if location:
                if location == "all":
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        total_visits.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                else:
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .eq("location", location)
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        total_visits.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit
            else:
                if flexologist == "all":
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        total_visits.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit
                else:
                    while True:
                        print(flexologist, "flexologist")
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .eq("flexologist_name", flexologist)
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        total_visits.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit
            print(len(total_visits), "total_visits")
            data = handle_total_visits(duration, total_visits, start_date, end_date)
            return jsonify({"status": "success", "data": data["data"]}), 200

        if dataset == "percentage_app_submission":
            all_bookings = []
            offset = 0
            limit = 1000
            print(get_config_id.data[0]["id"], "get_config_id")
            submitted_by_app = []
            if location:

                if location == "all":
                    while True:

                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        all_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    flexologists = (
                        supabase.table("users")
                        .select("*")
                        .eq("admin_id", user_id)
                        .eq("role_id", 3)
                        .execute()
                    )

                    for flexologist in flexologists.data:
                        limit = 1000
                        offset = 0
                        while True:
                            flexologist_bookings = (
                                supabase.table("clubready_bookings")
                                .select("*")
                                .eq("user_id", flexologist["id"])
                                .gte("created_at", start_date)
                                .lt("created_at", end_date)
                                .range(offset, offset + limit - 1)
                                .execute()
                            )

                            submitted_by_app_filter = [
                                item
                                for item in flexologist_bookings.data
                                if item["submitted"] == True
                            ]
                            submitted_by_app.extend(submitted_by_app_filter)
                            if len(flexologist_bookings.data) < limit:
                                break
                            offset += limit
                else:
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("location", location)
                            .eq("config_id", get_config_id.data[0]["id"])
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        all_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    limit = 1000
                    offset = 0
                    while True:
                        location_bookings = (
                            supabase.table("clubready_bookings")
                            .select("*")
                            .eq("location", location)
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        submitted_by_app_filter = [
                            item
                            for item in location_bookings.data
                            if item["submitted"] == True
                        ]
                        submitted_by_app.extend(submitted_by_app_filter)
                        if len(location_bookings.data) < limit:
                            break
                        offset += limit
            else:
                if flexologist == "all":
                    while True:

                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        all_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    flexologists = (
                        supabase.table("users")
                        .select("*")
                        .eq("admin_id", user_id)
                        .eq("role_id", 3)
                        .execute()
                    )

                    for flexologist in flexologists.data:
                        limit = 1000
                        offset = 0
                        while True:
                            flexologist_bookings = (
                                supabase.table("clubready_bookings")
                                .select("*")
                                .eq("user_id", flexologist["id"])
                                .gte("created_at", start_date)
                                .lt("created_at", end_date)
                                .range(offset, offset + limit - 1)
                                .execute()
                            )

                            submitted_by_app_filter = [
                                item
                                for item in flexologist_bookings.data
                                if item["submitted"] == True
                            ]
                            submitted_by_app.extend(submitted_by_app_filter)
                            if len(flexologist_bookings.data) < limit:
                                break
                            offset += limit
                else:
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("flexologist_name", flexologist)
                            .eq("config_id", get_config_id.data[0]["id"])
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        all_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit
                    limit = 1000
                    offset = 0
                    while True:
                        flexologist_bookings = (
                            supabase.table("clubready_bookings")
                            .select("*")
                            .eq("flexologist_name", flexologist)
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        submitted_by_app_filter = [
                            item
                            for item in flexologist_bookings.data
                            if item["submitted"] == True
                        ]
                        submitted_by_app.extend(submitted_by_app_filter)
                        if len(flexologist_bookings.data) < limit:
                            break
                        offset += limit

            data = handle_percentage_of_submitted_bookings(
                duration, all_bookings, submitted_by_app, start_date, end_date
            )
            return jsonify({"status": "success", "data": data["data"]}), 200
        if (
            dataset == "avg_1st_visit_quality_percentage"
            or dataset == "avg_subsequent_visit_quality_percentage"
        ):
            all_bookings = []
            gotten_bookings = []
            offset = 0
            limit = 1000
            first_timer = (
                "YES" if dataset == "avg_1st_visit_quality_percentage" else "NO"
            )
            get_config_id = (
                supabase.table("robot_process_automation_config")
                .select("id")
                .eq("admin_id", user_id)
                .execute()
            )
            if not get_config_id.data:
                return jsonify({"error": "No config id found", "status": "error"}), 400

            if location:
                if location == "all":
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .eq("first_timer", first_timer)
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        gotten_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    for booking in gotten_bookings:
                        score = (
                            int(booking["note_score"])
                            if booking["note_score"] != "N/A"
                            else 0
                        )
                        if score > 21:
                            print("score", score)
                        percentage = round(
                            (score / (18.0 if booking["first_timer"] == "YES" else 4.0))
                            * 100,
                            2,
                        )
                        booking["percentage"] = percentage
                        all_bookings.append(booking)

                else:
                    print(location, "location")
                    print(start_date, "start_date")
                    print(end_date, "end_date")
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .eq("first_timer", first_timer)
                            .eq("location", location)
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        gotten_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    for booking in gotten_bookings:
                        score = (
                            int(booking["note_score"])
                            if booking["note_score"] != "N/A"
                            else 0
                        )
                        percentage = round(
                            (score / (18.0 if booking["first_timer"] == "YES" else 4.0))
                            * 100,
                            2,
                        )
                        booking["percentage"] = percentage
                        all_bookings.append(booking)
            else:
                if flexologist == "all":
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .eq("first_timer", first_timer)
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        gotten_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    for booking in gotten_bookings:
                        score = (
                            int(booking["note_score"])
                            if booking["note_score"] != "N/A"
                            else 0
                        )
                        percentage = round(
                            (score / (18.0 if booking["first_timer"] == "YES" else 4.0))
                            * 100,
                            2,
                        )
                        booking["percentage"] = percentage
                        all_bookings.append(booking)
                else:
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .eq("flexologist_name", flexologist)
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        gotten_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    for booking in gotten_bookings:
                        score = (
                            int(booking["note_score"])
                            if booking["note_score"] != "N/A"
                            else 0
                        )
                        percentage = round(
                            (score / (18.0 if booking["first_timer"] == "YES" else 4.0))
                            * 100,
                            2,
                        )
                        booking["percentage"] = percentage
                        all_bookings.append(booking)

            print(len(all_bookings), "all_bookings")
            data = handle_avg_visit_quality_percentage(
                duration, all_bookings, start_date, end_date
            )
            return jsonify({"status": "success", "data": data["data"]}), 200

        if dataset == "avg_aggregate_note_quality_percentage":
            all_bookings = []
            gotten_bookings = []
            offset = 0
            limit = 1000
            get_config_id = (
                supabase.table("robot_process_automation_config")
                .select("id")
                .eq("admin_id", user_id)
                .execute()
            )
            if not get_config_id.data:
                return jsonify({"error": "No config id found", "status": "error"}), 400

            if location:
                if location == "all":
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        gotten_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    for booking in gotten_bookings:
                        score = (
                            int(booking["note_score"])
                            if booking["note_score"] != "N/A"
                            else 0
                        )
                        percentage = round(
                            (score / (18.0 if booking["first_timer"] == "YES" else 4.0))
                            * 100,
                            2,
                        )
                        booking["percentage"] = percentage
                        all_bookings.append(booking)

                else:
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .eq("location", location)
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        gotten_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit
                    for booking in gotten_bookings:
                        score = (
                            int(booking["note_score"])
                            if booking["note_score"] != "N/A"
                            else 0
                        )
                        percentage = round(
                            (score / (18.0 if booking["first_timer"] == "YES" else 4.0))
                            * 100,
                            2,
                        )
                        booking["percentage"] = percentage
                        all_bookings.append(booking)
            else:
                if flexologist == "all":
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        gotten_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    for booking in gotten_bookings:
                        score = (
                            int(booking["note_score"])
                            if booking["note_score"] != "N/A"
                            else 0
                        )
                        percentage = round(
                            (score / (18.0 if booking["first_timer"] == "YES" else 4.0))
                            * 100,
                            2,
                        )
                        booking["percentage"] = percentage
                        all_bookings.append(booking)
                else:
                    while True:
                        filter_data = (
                            supabase.table("robot_process_automation_notes_records")
                            .select("*")
                            .eq("config_id", get_config_id.data[0]["id"])
                            .eq("flexologist_name", flexologist)
                            .neq("status", "No Show")
                            .gte("created_at", start_date)
                            .lt("created_at", end_date)
                            .range(offset, offset + limit - 1)
                            .execute()
                        )
                        data = filter_data.data
                        gotten_bookings.extend(data)
                        if len(data) < limit:
                            break
                        offset += limit

                    for booking in gotten_bookings:
                        score = (
                            int(booking["note_score"])
                            if booking["note_score"] != "N/A"
                            else 0
                        )
                        percentage = round(
                            (score / (18.0 if booking["first_timer"] == "YES" else 4.0))
                            * 100,
                            2,
                        )
                        booking["percentage"] = percentage
                        all_bookings.append(booking)

            data = handle_avg_aggregate_note_quality_percentage(
                duration, all_bookings, start_date, end_date
            )
            return jsonify({"status": "success", "data": data["data"]}), 200
    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/second_row: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/third_row", methods=["GET"])
@require_bearer_token
def get_third_row(token):
    try:
        user_data = decode_jwt_token(token)
        user_id = user_data["user_id"]
        timezone_header = request.headers.get("X-Client-Timezone")
        today_date = datetime.now(timezone_header).strftime("%Y-%m-%d")
        flexologists = (
            supabase.table("users")
            .select("full_name, id, status, profile_picture_url, last_login")
            .eq("admin_id", user_id)
            .eq("role_id", 3)
            .in_("status", [1, 3, 4])
            .execute()
        )

        if flexologists.data:
            for flex in flexologists.data:
                bookings = (
                    supabase.table("clubready_bookings")
                    .select("*")
                    .eq("user_id", flex["id"])
                    .gte("created_at", today_date)
                    .execute()
                )

                if bookings.data:
                    flex["bookings"] = len(bookings.data)
                else:
                    flex["bookings"] = 0

        flexologists.data = sorted(
            flexologists.data, key=lambda x: x["bookings"], reverse=True
        )

        return jsonify({"status": "success", "data": flexologists.data}), 200
    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/third_row: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/fourth_row", methods=["GET"])
@require_bearer_token
def get_fourth_row(token):
    try:
        user_data = decode_jwt_token(token)
        user_id = user_data["user_id"]
        get_user_info = supabase.table("users").select("*").eq("id", user_id).execute()
        if not get_user_info.data:
            return jsonify({"error": "User not found", "status": "error"}), 404

        if get_user_info.data[0]["role_id"] not in [1, 2]:
            return jsonify({"error": "Unauthorized", "status": "error"}), 401

        businesses_info = supabase.table("businesses").select("*").execute()
        if not businesses_info.data:
            return jsonify({"error": "Businesses not found", "status": "error"}), 404
        business_information = []
        for business in businesses_info.data:
            business_username = business["username"]
            business_id = business["admin_id"]
            business_note_sub_status = business["note_taking_subscription_status"]
            business_rpa_sub_status = business[
                "robot_process_automation_subscription_status"
            ]
            business_created_at = business["created_at"]
            get_flexologists_info = (
                supabase.table("users")
                .select("*")
                .eq("admin_id", business["admin_id"])
                .eq("role_id", 3)
                .execute()
            )
            if not get_flexologists_info.data:
                buisness_flexologists_count = 0
            else:
                buisness_flexologists_count = len(get_flexologists_info.data)
            get_rpa_config_info = (
                supabase.table("robot_process_automation_config")
                .select("*")
                .eq("admin_id", business["admin_id"])
                .execute()
            )
            if not get_rpa_config_info.data:
                business_selected_locations = 0
            else:

                business_selected_locations = len(
                    json.loads(get_rpa_config_info.data[0]["selected_locations"])
                    if get_rpa_config_info.data[0]["selected_locations"]
                    else []
                )
            business_information.append(
                {
                    "business_username": business_username,
                    "business_id": business_id,
                    "business_note_sub_status": business_note_sub_status,
                    "business_rpa_sub_status": business_rpa_sub_status,
                    "business_created_at": business_created_at,
                    "buisness_flexologists_count": buisness_flexologists_count,
                }
            )

        return jsonify({"status": "success", "data": business_information}), 200
    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/fourth_row: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get_business_info", methods=["POST"])
@require_bearer_token
def get_business_info(token):
    try:
        user_data = decode_jwt_token(token)
        user_id = user_data["user_id"]
        data = request.json
        business_id = data["business_id"]

        if not business_id:
            return jsonify({"error": "Business ID is required", "status": "error"}), 400

        check_user_role = (
            supabase.table("users").select("*").eq("id", user_id).execute()
        )

        if check_user_role.data[0]["role_id"] not in [1, 2]:
            return jsonify({"error": "Unauthorized", "status": "error"}), 401

        get_business_info = (
            supabase.table("businesses")
            .select("*")
            .eq("admin_id", business_id)
            .execute()
        )

        if not get_business_info.data:
            return jsonify({"error": "Business not found", "status": "error"}), 404

        business_info = get_business_info.data[0]

        business_username = business_info["username"]
        business_note_sub_status = business_info["note_taking_subscription_status"]
        business_rpa_sub_status = business_info[
            "robot_process_automation_subscription_status"
        ]
        business_created_at = business_info["created_at"]

        get_flexologists_info = (
            supabase.table("users")
            .select("full_name, id, status, profile_picture_url, last_login")
            .eq("admin_id", business_id)
            .eq("role_id", 3)
            .execute()
        )

        if not get_flexologists_info.data:
            business_flexologists_count = 0
            business_flexologists_info = []
        else:
            business_flexologists_count = len(get_flexologists_info.data)
            business_flexologists_info = get_flexologists_info.data

        get_rpa_config_info = (
            supabase.table("robot_process_automation_config")
            .select("*")
            .eq("admin_id", business_id)
            .execute()
        )

        if not get_rpa_config_info.data:
            business_selected_locations = None
            business_all_locations = None
        else:
            business_all_locations = (
                json.loads(get_rpa_config_info.data[0]["locations"])
                if get_rpa_config_info.data[0]["locations"]
                else None
            )
            business_selected_locations = (
                json.loads(get_rpa_config_info.data[0]["selected_locations"])
                if get_rpa_config_info.data[0]["selected_locations"]
                else None
            )

        if get_business_info.data[0]["note_taking_subscription_id"]:
            note_taking_sub = get_business_info.data[0]["note_taking_subscription_id"]
            note_taking_sub_details = get_subscription_details(note_taking_sub)
            business_note_sub_details = {
                "price": note_taking_sub_details["items"]["data"][0]["price"][
                    "unit_amount"
                ],
                "currency": note_taking_sub_details["items"]["data"][0]["price"][
                    "currency"
                ],
                "quantity": note_taking_sub_details["items"]["data"][0]["quantity"],
                "interval": note_taking_sub_details["plan"]["interval"],
                "status": note_taking_sub_details["status"],
                "start_date": note_taking_sub_details["items"]["data"][0][
                    "current_period_start"
                ],
                "end_date": note_taking_sub_details["items"]["data"][0][
                    "current_period_end"
                ],
            }
        else:
            business_note_sub_details = None

        if get_business_info.data[0]["robot_process_automation_subscription_id"]:
            robot_process_automation_sub = get_business_info.data[0][
                "robot_process_automation_subscription_id"
            ]
            robot_process_automation_sub_details = get_subscription_details(
                robot_process_automation_sub
            )
            business_rpa_sub_details = {
                "price": robot_process_automation_sub_details["items"]["data"][0][
                    "price"
                ]["unit_amount"],
                "currency": robot_process_automation_sub_details["items"]["data"][0][
                    "price"
                ]["currency"],
                "quantity": robot_process_automation_sub_details["items"]["data"][0][
                    "quantity"
                ],
                "interval": robot_process_automation_sub_details["plan"]["interval"],
                "status": robot_process_automation_sub_details["status"],
                "start_date": robot_process_automation_sub_details["items"]["data"][0][
                    "current_period_start"
                ],
                "end_date": robot_process_automation_sub_details["items"]["data"][0][
                    "current_period_end"
                ],
            }
        else:
            business_rpa_sub_details = None

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "business_username": business_username,
                        "business_note_sub_status": business_note_sub_status,
                        "business_rpa_sub_status": business_rpa_sub_status,
                        "business_created_at": business_created_at,
                        "business_flexologists_count": business_flexologists_count,
                        "business_all_locations": business_all_locations,
                        "business_selected_locations": business_selected_locations,
                        "business_note_sub_details": business_note_sub_details,
                        "business_rpa_sub_details": business_rpa_sub_details,
                        "business_flexologists_info": business_flexologists_info,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/get_business_info: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


def init_dashboard_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/admin/dashboard")
