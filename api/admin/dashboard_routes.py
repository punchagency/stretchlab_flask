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
import asyncio
from concurrent.futures import ThreadPoolExecutor


routes = Blueprint("dashboard", __name__)


def get_bookings_info(token):
    try:
        user_data = decode_jwt_token(token)
        
        # Get user's admin_id
        user_info = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .single()
            .execute()
        )
        user_id = user_info.data["admin_id"]

        # Get business info
        business = (
            supabase.table("businesses")
            .select("admin_id, username")
            .eq("admin_id", user_id)
            .single()
            .execute()
        )
        
        if not business.data:
            return jsonify({"message": "Business not found", "status": "error"}), 404

        business_admin_id = business.data["admin_id"]
        business_name = business.data["username"]

        # Get config_id
        config = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", business_admin_id)
            .single()
            .execute()
        )
        
        if not config.data:
            return jsonify({"message": "No config id found", "status": "error"}), 404

        config_id = config.data["id"]

        # Calculate date ranges
        first_day_this_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first_day_last_month = (first_day_this_month - timedelta(days=1)).replace(day=1)
        year = first_day_this_month.year
        month = first_day_this_month.month
        num_days = monthrange(year, month)[1]
        first_day_next_month = first_day_this_month + timedelta(days=num_days)

        # Use COUNT instead of fetching all records
        bookings_this_month = (
            supabase.table("robot_process_automation_notes_records")
            .select("*", count="exact")
            .eq("config_id", config_id)
            .gte("created_at", first_day_this_month.strftime("%Y-%m-%d"))
            .lt("created_at", first_day_next_month.strftime("%Y-%m-%d"))
            .execute()
        )
        bookings_in_month = bookings_this_month.count if bookings_this_month.count is not None else 0

        bookings_last_month = (
            supabase.table("robot_process_automation_notes_records")
            .select("*", count="exact")
            .eq("config_id", config_id)
            .gte("created_at", first_day_last_month.strftime("%Y-%m-%d"))
            .lt("created_at", first_day_this_month.strftime("%Y-%m-%d"))
            .execute()
        )
        bookings_in_last_month = bookings_last_month.count if bookings_last_month.count is not None else 0

        # Calculate aggregation
        if bookings_in_month == 0 and bookings_in_last_month == 0:
            aggregation = 0
        elif bookings_in_last_month == 0:
            aggregation = bookings_in_month * 100  # Simplified: avoids division by 1
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
            "aggregation": round(aggregation, 2),  # Round for cleaner output
            "upwards_trend": aggregation > 0,
            "neutral_trend": aggregation == 0,
        }

        return bookings_info
        
    except Exception as e:
        logging.error(f"Error in get_bookings_info: {str(e)}")
        return {"error": str(e)} 

def number_of_subscribed(user_id):
    try:
        # Single query to get all business subscription info at once
        businesses = (
            supabase.table("businesses")
            .select("admin_id, note_taking_active, robot_process_automation_active")
            .execute()
        )
        
        note_active_ids = set()
        rpa_active_ids = set()
        
        for business in (businesses.data or []):
            if business.get("note_taking_active"):
                note_active_ids.add(business["admin_id"])
            if business.get("robot_process_automation_active"):
                rpa_active_ids.add(business["admin_id"])
        
        any_active_ids = note_active_ids.union(rpa_active_ids)

        # Get subscribed flexologists
        subscribed_flexologists = (
            supabase.table("users")
            .select("id")
            .in_("role_id", [3, 8])
            .eq("status", 1)
            .neq("admin_id", user_id)
            .execute()
        )

        number_of_subscribed_flexologists = len(subscribed_flexologists.data or [])
        
        subscribed_locations = 0
        average_number_of_locations_per_business = 0
        
        if rpa_active_ids:
            # Single query to get ALL locations at once instead of looping
            rpa_active_list = list(rpa_active_ids)
            locations_query = (
                supabase.table("robot_process_automation_config")
                .select("selected_locations")
                .in_("admin_id", rpa_active_list)
                .execute()
            )
            
            for location_record in (locations_query.data or []):
                if location_record.get("selected_locations"):
                    try:
                        locations = json.loads(location_record["selected_locations"])
                        subscribed_locations += len(locations) if isinstance(locations, list) else 0
                    except (json.JSONDecodeError, TypeError):
                        continue
            
            average_number_of_locations_per_business = (
                subscribed_locations / len(rpa_active_ids) if rpa_active_ids else 0
            )

        return {
            "note_taking_active_count": len(note_active_ids),
            "rpa_active_count": len(rpa_active_ids),
            "unique_businesses_with_any_subscription": len(any_active_ids),
            "number_of_subscribed_flexologists": number_of_subscribed_flexologists,
            "number_of_subscribed_locations": subscribed_locations,
            "average_number_of_locations_per_business": round(average_number_of_locations_per_business, 2),
        }
        
    except Exception as e:
        logging.error(f"Error in number_of_subscribed: {str(e)}")
        return {"error": str(e)}

@routes.route("/first_row", methods=["GET"])
@require_bearer_token
def get_first_row(token):
    try:
        user_data = decode_jwt_token(token)
        if user_data["role_id"] == 3:
            return jsonify({
                "error": "You are not authorized to see this page",
                "status": "error",
            }), 401

        show_others = user_data["role_id"] == 1
        
        # Execute queries in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Always fetch bookings_info
            bookings_future = executor.submit(get_bookings_info, token)
            
            # Only fetch these if needed
            if show_others:
                balance_future = executor.submit(get_balance_for_month)
                subscriptions_future = executor.submit(number_of_subscribed, user_data["user_id"])
            
            # Wait for results
            bookings_info = bookings_future.result()
            
            data_to_send = {
                "bookings_info": bookings_info,
            }
            
            if show_others:
                data_to_send["balance_info"] = balance_future.result()
                data_to_send["subscriptions_info"] = subscriptions_future.result()

        return jsonify({
            "status": "success",
            "data": data_to_send,
        }), 200

    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/first_row: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500

@routes.route("/activities", methods=["GET"])
@require_bearer_token
def get_activities(token):
    try:
        user_data = decode_jwt_token(token)
        if user_data["role_id"] == 3:
            return jsonify({
                "error": "You are not authorized to see this page",
                "status": "error",
            }), 401

        # Get user's admin_id
        user_info = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .single()
            .execute()
        )
        user_id = user_info.data["admin_id"]

        # Get all flexologist IDs
        flexologists = (
            supabase.table("users")
            .select("id")
            .eq("role_id", 3)
            .eq("admin_id", user_id)
            .execute()
        )

        notes_submitted_with_app = None
        notes_submitted_per_flexologist = None
        notes_submitted_per_location = None

        if flexologists.data:
            flexologist_ids = [f["id"] for f in flexologists.data]
            
            # Fetch ALL records with pagination, but in ONE query per batch instead of per flexologist
            all_notes_submitted = []
            offset = 0
            limit = 1000
            
            while True:
                notes_submitted = (
                    supabase.table("clubready_bookings")
                    .select("flexologist_name, location")
                    .eq("submitted", True)
                    .in_("user_id", flexologist_ids)
                    .range(offset, offset + limit - 1)
                    .execute()
                )
                all_notes_submitted.extend(notes_submitted.data)
                
                if len(notes_submitted.data) < limit:
                    break
                offset += limit
            
            if all_notes_submitted:
                from collections import defaultdict
                notes_submitted_per_flexologist = defaultdict(int)
                notes_submitted_per_location = defaultdict(int)
                
                for booking in all_notes_submitted:
                    notes_submitted_per_flexologist[booking["flexologist_name"].lower()] += 1
                    notes_submitted_per_location[booking["location"].lower()] += 1
                
                notes_submitted_per_flexologist = dict(notes_submitted_per_flexologist)
                notes_submitted_per_location = dict(notes_submitted_per_location)
                notes_submitted_with_app = len(all_notes_submitted)
            else:
                notes_submitted_with_app = 0
                notes_submitted_per_flexologist = {}
                notes_submitted_per_location = {}

        # Get config and analyzed bookings
        config_result = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", user_id)
            .single()
            .execute()
        )

        total_analysed_bookings = None
        notes_analysed_per_location = None
        notes_analysed_per_flexologist = None

        if config_result.data:
            # Fetch ALL records with pagination
            all_analysed_bookings = []
            offset = 0
            limit = 1000
            
            while True:
                analysed_bookings = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("flexologist_name, location")
                    .eq("config_id", config_result.data["id"])
                    .range(offset, offset + limit - 1)
                    .execute()
                )
                all_analysed_bookings.extend(analysed_bookings.data)
                
                if len(analysed_bookings.data) < limit:
                    break
                offset += limit

            if all_analysed_bookings:
                from collections import defaultdict
                notes_analysed_per_location = defaultdict(int)
                notes_analysed_per_flexologist = defaultdict(int)
                
                for booking in all_analysed_bookings:
                    notes_analysed_per_location[booking["location"]] += 1
                    notes_analysed_per_flexologist[booking["flexologist_name"]] += 1
                
                notes_analysed_per_location = dict(notes_analysed_per_location)
                notes_analysed_per_flexologist = dict(notes_analysed_per_flexologist)
                total_analysed_bookings = len(all_analysed_bookings)
            else:
                total_analysed_bookings = 0
                notes_analysed_per_location = {}
                notes_analysed_per_flexologist = {}

        return jsonify({
            "status": "success",
            "data": {
                "notes_submitted_with_app": notes_submitted_with_app,
                "total_analysed_bookings": total_analysed_bookings,
                "notes_analysed_per_location": notes_analysed_per_location,
                "notes_analysed_per_flexologist": notes_analysed_per_flexologist,
                "notes_submitted_per_flexologist": notes_submitted_per_flexologist,
                "notes_submitted_per_location": notes_submitted_per_location,
            },
        }), 200

    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/activities: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500

@routes.route("/get_chart_filters", methods=["GET"])
@require_bearer_token
def get_chart_filters(token):
    try:
        user_data = decode_jwt_token(token)
        if user_data["role_id"] == 3:
            return jsonify({
                "error": "You are not authorized to see this page",
                "status": "error",
            }), 401

        user_id = user_data["user_id"]
        filter_by = request.args.get("filter_by", None)

        # Single query to get user info
        user_info = (
            supabase.table("users")
            .select("role_id, username, admin_id")
            .eq("id", user_id)
            .single()
            .execute()
        )
        
        role_id = user_info.data["role_id"]
        
        if role_id not in [1, 2, 4, 8]:
            return jsonify({
                "error": "You are not authorized to see this page",
                "status": "error",
            }), 401

        # Determine the admin_id to use
        admin_id = user_info.data["admin_id"] if role_id in [4, 8] else user_id
        if role_id in [4, 8] and not admin_id:
            return jsonify({"error": "No admin user found", "status": "error"}), 404

        # Parallel queries using RPC or batch approach
        # Query 1: Get config_id
        config_result = (
            supabase.table("robot_process_automation_config")
            .select("id, selected_locations")
            .eq("admin_id", admin_id)
            .single()
            .execute()
        )

        if not config_result.data:
            return jsonify({"error": "No config id found", "status": "error"}), 400

        config_id = config_result.data["id"]
        locations = (
            json.loads(config_result.data["selected_locations"])
            if config_result.data["selected_locations"]
            else []
        )

        # Query 2: Get distinct flexologists
        flexologists_result = (
            supabase.table("robot_process_automation_notes_records")
            .select("flexologist_name")
            .eq("config_id", config_id)
            .execute()
        )
        
        flexologists = sorted(set(
            f["flexologist_name"] 
            for f in flexologists_result.data 
            if f.get("flexologist_name")
        )) if flexologists_result.data else []

        # Query 3: Get business info
        business_info = (
            supabase.table("businesses")
            .select("note_taking_active")
            .eq("admin_id", admin_id)
            .single()
            .execute()
        )

        # Build filters 
        if not filter_by:
            filters = [
                {"label": "Total Client Visits", "value": "total_client_visits"},
                {"label": "Avg Note Quality %", "value": "avg_"},
            ]
        else:
            filters = [
                {"label": "Total Client Visits", "value": "total_client_visits"},
                {"label": "Avg. Note Quality %", "value": "note_quality_percentage"},
            ]

        if business_info.data["note_taking_active"] or role_id == 1:
            filters = [
                {"label": "% App Submissions", "value": "percentage_app_submission"},
            ] + filters

        return jsonify({
            "status": "success",
            "data": {
                "flexologists": flexologists,
                "locations": locations,
                "filters": filters,
            }
        }), 200

    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/get_chart_filters: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500

@routes.route("/second_row", methods=["GET"])
@require_bearer_token
def get_second_row(token):
    try:
        user_data = decode_jwt_token(token)
        if user_data["role_id"] == 3:
            return (
                jsonify(
                    {
                        "error": "You are not authorized to see this page",
                        "status": "error",
                    }
                ),
                401,
            )
        user_id = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .execute()
        ).data[0]["admin_id"]
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

        def fetch_total_visits(supabase, get_config_id, start_date, end_date, location=None, flexologist=None, limit=1000):
            total_visits = []

            # Base query
            base_query = (
                supabase.table("robot_process_automation_notes_records")
                .select("appointment_date")
                .eq("config_id", get_config_id.data[0]["id"])
                .neq("status", "No Show")
                .gte("appointment_date", start_date)
                .lt("appointment_date", end_date)
            )

            # Apply filters conditionally
            if location:
                if location != "all":
                    base_query = base_query.eq("location", location)
            elif flexologist:
                if flexologist != "all":
                    base_query = base_query.eq("flexologist_name", flexologist)

            # Paginate
            offset = 0
            while True:
                result = base_query.range(offset, offset + limit - 1).execute()
                data = result.data or []
                total_visits.extend(data)
                if len(data) < limit:
                    break
                offset += limit

            return total_visits

        def fetch_quality_bookings(supabase, get_config_id, start_date, end_date, first_timer, location=None, flexologist=None, limit=1000):
            all_bookings = []

            # Base query
            base_query = (
                supabase.table("robot_process_automation_notes_records")
                .select("first_timer, note_score, appointment_date")
                .eq("config_id", get_config_id.data[0]["id"])
                .eq("first_timer", first_timer)
                .neq("status", "No Show")
                .gte("appointment_date", start_date)
                .lt("appointment_date", end_date)
            )

            # Apply filters conditionally
            if location:
                if location != "all":
                    base_query = base_query.eq("location", location)
            elif flexologist:
                if flexologist != "all":
                    base_query = base_query.eq("flexologist_name", flexologist)

            # Paginate and process
            offset = 0
            while True:
                result = base_query.range(offset, offset + limit - 1).execute()
                data = result.data or []

                # Calculate percentage for each booking
                for booking in data:
                    score = (
                        int(booking["note_score"])
                        if booking["note_score"] != "N/A"
                        else 0
                    )

                    percentage = round(
                        (score / (16.0 if booking["first_timer"] == "YES" else 4.0))
                        * 100,
                        2,
                    )
                    booking["percentage"] = percentage
                    all_bookings.append(booking)

                if len(data) < limit:
                    break
                offset += limit

            return all_bookings

        def fetch_aggregate_quality_bookings(supabase, get_config_id, start_date, end_date, location=None, flexologist=None, limit=1000):
            all_bookings = []

            # Base query (no first_timer filter for aggregate)
            base_query = (
                supabase.table("robot_process_automation_notes_records")
                .select("first_timer, note_score, appointment_date")
                .eq("config_id", get_config_id.data[0]["id"])
                .neq("status", "No Show")
                .gte("appointment_date", start_date)
                .lt("appointment_date", end_date)
            )

            # Apply filters conditionally
            if location:
                if location != "all":
                    base_query = base_query.eq("location", location)
            elif flexologist:
                if flexologist != "all":
                    base_query = base_query.eq("flexologist_name", flexologist)

            # Paginate and process
            offset = 0
            while True:
                result = base_query.range(offset, offset + limit - 1).execute()
                data = result.data or []

                # Calculate percentage for each booking
                for booking in data:
                    score = (
                        int(booking["note_score"])
                        if booking["note_score"] != "N/A"
                        else 0
                    )

                    percentage = round(
                        (score / (16.0 if booking["first_timer"] == "YES" else 4.0))
                        * 100,
                        2,
                    )
                    booking["percentage"] = percentage
                    all_bookings.append(booking)

                if len(data) < limit:
                    break
                offset += limit

            return all_bookings

        if dataset == "total_client_visits":
            total_visits = fetch_total_visits(supabase, get_config_id, start_date, end_date, location, flexologist)

            data = handle_total_visits(duration, total_visits, start_date, end_date)
            return jsonify({"status": "success", "data": data["data"]}), 200

        if dataset == "percentage_app_submission":
            def fetch_paginated_data(query, limit=1000):
                """Fetch all data from a Supabase query using pagination."""
                all_data = []
                offset = 0
                while True:
                    result = query.range(offset, offset + limit - 1).execute()
                    data = result.data or []
                    all_data.extend(data)
                    if len(data) < limit:
                        break
                    offset += limit
                return all_data

            def fetch_bookings(supabase, user_id, get_config_id, start_date, end_date, location=None, flexologist=None):
                all_bookings = []
                submitted_by_app = []
                limit = 1000

                # Common base for robot_process_automation_notes_records
                base_notes_query = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("appointment_date")
                    .eq("config_id", get_config_id.data[0]["id"])
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                )

                # Common base for clubready_bookings
                base_bookings_query = (
                    supabase.table("clubready_bookings")
                    .select("created_at, submitted, booking_time")
                    .gte("created_at", start_date)
                    .lt("created_at", end_date)
                    .eq("submitted", True)  # Move filter into SQL instead of Python
                )

                # ----------------------------
                # Case 1: Location is provided
                # ----------------------------
                if location:
                    if location == "all":
                        # Fetch all locations' notes
                        all_bookings.extend(fetch_paginated_data(base_notes_query, limit))

                        # Fetch all flexologists for this admin
                        flexologists = (
                            supabase.table("users")
                            .select("id")
                            .eq("admin_id", user_id)
                            .eq("role_id", 3)
                            .execute()
                        ).data

                        if flexologists:
                            flexologist_ids = [f["id"] for f in flexologists]

                            # Batch IDs to respect Supabase filter size
                            for i in range(0, len(flexologist_ids), 1000):
                                batch_ids = flexologist_ids[i:i+1000]
                                flexologist_query = base_bookings_query.in_("user_id", batch_ids)
                                submitted_by_app.extend(fetch_paginated_data(flexologist_query, limit))

                    else:
                        # Specific location
                        location_notes_query = base_notes_query.eq("location", location)
                        all_bookings.extend(fetch_paginated_data(location_notes_query, limit))

                        location_bookings_query = base_bookings_query.eq("location", location)
                        submitted_by_app.extend(fetch_paginated_data(location_bookings_query, limit))

                # ----------------------------
                # Case 2: Flexologist is provided
                # ----------------------------
                else:
                    if flexologist == "all":
                        # Fetch all notes (all flexologists)
                        all_bookings.extend(fetch_paginated_data(base_notes_query, limit))

                        # Get all flexologists for this admin
                        flexologists = (
                            supabase.table("users")
                            .select("id")
                            .eq("admin_id", user_id)
                            .eq("role_id", 3)
                            .execute()
                        ).data

                        if flexologists:
                            flexologist_ids = [f["id"] for f in flexologists]
                            for i in range(0, len(flexologist_ids), 1000):
                                batch_ids = flexologist_ids[i:i+1000]
                                flexologist_query = base_bookings_query.in_("user_id", batch_ids)
                                submitted_by_app.extend(fetch_paginated_data(flexologist_query, limit))
                    else:
                        # Specific flexologist
                        flexologist_notes_query = base_notes_query.eq("flexologist_name", flexologist)
                        all_bookings.extend(fetch_paginated_data(flexologist_notes_query, limit))

                        flexologist_bookings_query = base_bookings_query.eq("flexologist_name", flexologist)
                        submitted_by_app.extend(fetch_paginated_data(flexologist_bookings_query, limit))

                return all_bookings, submitted_by_app

            all_bookings, submitted_by_app = fetch_bookings(supabase, user_id, get_config_id, start_date, end_date, location, flexologist)
            data = handle_percentage_of_submitted_bookings(
                duration, all_bookings, submitted_by_app, start_date, end_date
            )
            return jsonify({"status": "success", "data": data["data"]}), 200
        if (
            dataset == "avg_1st_visit_quality_percentage"
            or dataset == "avg_subsequent_visit_quality_percentage"
        ):
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

            all_bookings = fetch_quality_bookings(supabase, get_config_id, start_date, end_date, first_timer, location, flexologist)

            data = handle_avg_visit_quality_percentage(
                duration, all_bookings, start_date, end_date
            )
            return jsonify({"status": "success", "data": data["data"]}), 200

        if dataset == "avg_aggregate_note_quality_percentage":
            get_config_id = (
                supabase.table("robot_process_automation_config")
                .select("id")
                .eq("admin_id", user_id)
                .execute()
            )
            if not get_config_id.data:
                return jsonify({"error": "No config id found", "status": "error"}), 400

            all_bookings = fetch_aggregate_quality_bookings(supabase, get_config_id, start_date, end_date, location, flexologist)

            data = handle_avg_aggregate_note_quality_percentage(
                duration, all_bookings, start_date, end_date
            )
            return jsonify({"status": "success", "data": data["data"]}), 200

        return jsonify({"message": "Invalid filter", "status": "error"}), 404
    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/second_row: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/third_row", methods=["GET"])
@require_bearer_token
def get_third_row(token):
    try:
        user_data = decode_jwt_token(token)
        duration = request.args.get("duration", "this_year")

        # Get user's admin_id
        user_info = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .single()
            .execute()
        )
        user_id = user_info.data["admin_id"]

        # Get flexologists
        flexologists = (
            supabase.table("users")
            .select("full_name, id, status, profile_picture_url, last_login")
            .eq("admin_id", user_id)
            .in_("role_id", [3, 8])
            .in_("status", [1, 3, 4])
            .execute()
        )

        if not flexologists.data:
            return jsonify({"status": "success", "data": []}), 200

        # Get date range
        if duration == "custom":
            start_date_str = request.args.get("start_date")
            end_date_str = request.args.get("end_date")
            if not start_date_str or not end_date_str:
                return jsonify({
                    "error": "Start and end date are required",
                    "status": "error"
                }), 400
            start_date, end_date = get_start_and_end_date(
                duration, start_date_str, end_date_str
            )
        else:
            start_date, end_date = get_start_and_end_date(duration)

        # Get ALL bookings for ALL flexologists in ONE query
        flexologist_ids = [flex["id"] for flex in flexologists.data]
        
        all_bookings = (
            supabase.table("clubready_bookings")
            .select("user_id, submitted")
            .in_("user_id", flexologist_ids)
            .gte("created_at", start_date)
            .lt("created_at", end_date)
            .execute()
        )

        # Group bookings by flexologist using a dictionary
        from collections import defaultdict
        bookings_by_flex = defaultdict(lambda: {"total": 0, "submitted": 0})
        
        for booking in (all_bookings.data or []):
            user_id = booking["user_id"]
            bookings_by_flex[user_id]["total"] += 1
            if booking.get("submitted"):
                bookings_by_flex[user_id]["submitted"] += 1

        # Add booking stats to each flexologist
        for flex in flexologists.data:
            flex_id = flex["id"]
            stats = bookings_by_flex[flex_id]
            
            flex["bookings"] = stats["total"]
            flex["submitted_bookings"] = stats["submitted"]
            flex["percentage_submitted_bookings"] = (
                round((stats["submitted"] / stats["total"]) * 100, 2)
                if stats["total"] > 0
                else 0
            )

        # Sort by bookings (descending)
        flexologists.data.sort(key=lambda x: x["bookings"], reverse=True)

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
        
        # Get user info
        get_user_info = (
            supabase.table("users")
            .select("role_id")
            .eq("id", user_id)
            .single()
            .execute()
        )
        
        if not get_user_info.data:
            return jsonify({"error": "User not found", "status": "error"}), 404

        if get_user_info.data["role_id"] not in [1, 2, 4, 8]:
            return jsonify({"error": "Unauthorized", "status": "error"}), 401

        # Get all businesses
        businesses_info = supabase.table("businesses").select("*").execute()
        
        if not businesses_info.data:
            return jsonify({"error": "Businesses not found", "status": "error"}), 404

        # Get all business IDs
        business_ids = [business["admin_id"] for business in businesses_info.data]

        # Fetch ALL flexologists for ALL businesses in ONE query
        all_flexologists = (
            supabase.table("users")
            .select("admin_id, id")
            .in_("admin_id", business_ids)
            .in_("role_id", [3, 8])
            .eq("status", 1)
            .execute()
        )

        # Group flexologists by business (admin_id)
        from collections import defaultdict
        flexologists_by_business = defaultdict(int)
        for flex in (all_flexologists.data or []):
            flexologists_by_business[flex["admin_id"]] += 1

        # Fetch ALL RPA configs for ALL businesses in ONE query
        all_rpa_configs = (
            supabase.table("robot_process_automation_config")
            .select("admin_id, selected_locations")
            .in_("admin_id", business_ids)
            .execute()
        )

        # Group RPA configs by business
        rpa_configs_by_business = {}
        for config in (all_rpa_configs.data or []):
            admin_id = config["admin_id"]
            try:
                locations = json.loads(config["selected_locations"]) if config.get("selected_locations") else []
                rpa_configs_by_business[admin_id] = len(locations) if isinstance(locations, list) else 0
            except (json.JSONDecodeError, TypeError):
                rpa_configs_by_business[admin_id] = 0

        # Build business information using pre-fetched data
        business_information = []
        for business in businesses_info.data:
            business_id = business["admin_id"]
            
            business_information.append({
                "business_username": business["username"],
                "business_id": business_id,
                "business_note_sub_status": business["note_taking_subscription_status"],
                "business_rpa_sub_status": business["robot_process_automation_subscription_status"],
                "business_created_at": business["created_at"],
                "buisness_flexologists_count": flexologists_by_business.get(business_id, 0),
                "business_selected_locations": rpa_configs_by_business.get(business_id, 0),
            })

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
        business_id = data.get("business_id")

        if not business_id:
            return jsonify({"error": "Business ID is required", "status": "error"}), 400

        # Check user role - only fetch role_id
        check_user_role = (
            supabase.table("users")
            .select("role_id")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if check_user_role.data["role_id"] not in [1]:
            return jsonify({"error": "Unauthorized", "status": "error"}), 401

        # Get business info
        get_business_info = (
            supabase.table("businesses")
            .select("*")
            .eq("admin_id", business_id)
            .single()
            .execute()
        )

        if not get_business_info.data:
            return jsonify({"error": "Business not found", "status": "error"}), 404

        business_info = get_business_info.data

        business_username = business_info["username"]
        business_note_sub_status = business_info["note_taking_subscription_status"]
        business_rpa_sub_status = business_info["robot_process_automation_subscription_status"]
        business_created_at = business_info["created_at"]

        # Get flexologists
        get_flexologists_info = (
            supabase.table("users")
            .select("full_name, id, status, profile_picture_url, last_login")
            .eq("admin_id", business_id)
            .in_("role_id", [3, 8])
            .execute()
        )

        business_flexologists_count = 0
        business_flexologists_info = []
        locations_summary = []

        if get_flexologists_info.data:
            business_flexologists_count = len(get_flexologists_info.data)
            business_flexologists_info = get_flexologists_info.data

            # Calculate date range
            current_date = datetime.now()
            end_date = (current_date - timedelta(days=1)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
            start_date = (end_date - timedelta(days=30)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            # Get ALL bookings for ALL flexologists in ONE query
            flexologist_ids = [flex["id"] for flex in get_flexologists_info.data]
            
            all_bookings = (
                supabase.table("clubready_bookings")
                .select("user_id, submitted, location")
                .in_("user_id", flexologist_ids)
                .gte("created_at", start_date)
                .lt("created_at", end_date)
                .execute()
            )

            # Build a mapping: flexologist_id -> name
            flex_id_to_name = {
                flex["id"]: flex.get("full_name") 
                for flex in get_flexologists_info.data
            }

            # Aggregate bookings by location and flexologist
            # Structure: location -> flexologist_id -> {total, submitted}
            from collections import defaultdict
            location_data = defaultdict(lambda: {
                "location": None,
                "flexologists": defaultdict(lambda: {"total": 0, "submitted": 0}),
                "total_bookings_in_location": 0,
                "total_submitted_by_location": 0,
            })

            for booking in (all_bookings.data or []):
                loc = booking.get("location")
                if not loc:
                    continue
                
                user_id_booking = booking["user_id"]
                is_submitted = bool(booking.get("submitted"))
                
                # Initialize location if first time seeing it
                if location_data[loc]["location"] is None:
                    location_data[loc]["location"] = loc
                
                # Update flexologist stats
                location_data[loc]["flexologists"][user_id_booking]["total"] += 1
                if is_submitted:
                    location_data[loc]["flexologists"][user_id_booking]["submitted"] += 1
                
                # Update location totals
                location_data[loc]["total_bookings_in_location"] += 1
                if is_submitted:
                    location_data[loc]["total_submitted_by_location"] += 1

            # Convert to final format
            locations_summary = []
            for loc, data in location_data.items():
                flexologists_list = [
                    {
                        "name": flex_id_to_name.get(flex_id),
                        "total_bookings": counts["total"],
                        "total_submitted": counts["submitted"],
                    }
                    for flex_id, counts in data["flexologists"].items()
                ]
                
                locations_summary.append({
                    "location": loc,
                    "flexologists": flexologists_list,
                    "total_bookings_in_location": data["total_bookings_in_location"],
                    "total_submitted_by_location": data["total_submitted_by_location"],
                })

        # Get RPA config info
        get_rpa_config_info = (
            supabase.table("robot_process_automation_config")
            .select("locations, selected_locations")
            .eq("admin_id", business_id)
            .single()
            .execute()
        )

        if not get_rpa_config_info.data:
            business_selected_locations = None
            business_all_locations = None
        else:
            try:
                business_all_locations = (
                    json.loads(get_rpa_config_info.data["locations"])
                    if get_rpa_config_info.data.get("locations")
                    else None
                )
                business_selected_locations = (
                    json.loads(get_rpa_config_info.data["selected_locations"])
                    if get_rpa_config_info.data.get("selected_locations")
                    else None
                )
            except (json.JSONDecodeError, TypeError):
                business_all_locations = None
                business_selected_locations = None

        # Get subscription details
        business_note_sub_details = None
        if business_info.get("note_taking_subscription_id"):
            note_taking_sub_details = get_subscription_details(
                business_info["note_taking_subscription_id"]
            )
            business_note_sub_details = {
                "price": note_taking_sub_details["items"]["data"][0]["price"]["unit_amount"],
                "currency": note_taking_sub_details["items"]["data"][0]["price"]["currency"],
                "quantity": note_taking_sub_details["items"]["data"][0]["quantity"],
                "interval": note_taking_sub_details["plan"]["interval"],
                "status": note_taking_sub_details["status"],
                "start_date": note_taking_sub_details["items"]["data"][0]["current_period_start"],
                "end_date": note_taking_sub_details["items"]["data"][0]["current_period_end"],
            }

        business_rpa_sub_details = None
        if business_info.get("robot_process_automation_subscription_id"):
            robot_process_automation_sub_details = get_subscription_details(
                business_info["robot_process_automation_subscription_id"]
            )
            business_rpa_sub_details = {
                "price": robot_process_automation_sub_details["items"]["data"][0]["price"]["unit_amount"],
                "currency": robot_process_automation_sub_details["items"]["data"][0]["price"]["currency"],
                "quantity": robot_process_automation_sub_details["items"]["data"][0]["quantity"],
                "interval": robot_process_automation_sub_details["plan"]["interval"],
                "status": robot_process_automation_sub_details["status"],
                "start_date": robot_process_automation_sub_details["items"]["data"][0]["current_period_start"],
                "end_date": robot_process_automation_sub_details["items"]["data"][0]["current_period_end"],
            }

        return jsonify({
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
                "locations_summary": locations_summary,
            },
        }), 200

    except Exception as e:
        logging.error(f"Error in POST api/admin/dashboard/get_business_info: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500

def init_dashboard_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/admin/dashboard")
