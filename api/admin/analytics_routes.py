from flask import Blueprint, jsonify, request
from ..utils.middleware import require_bearer_token
from datetime import datetime, timedelta
import logging
from ..utils.utils import decode_jwt_token
from ..utils.analytics import get_start_and_end_date
import json

routes = Blueprint("analytics_routes", __name__)


@routes.route("/rpa_audit", methods=["GET"])
@require_bearer_token
def rpa_audit(token):
    try:
        user_data = decode_jwt_token(token)
        duration = request.args.get("duration")
        location = request.args.get("location")
        filter_metric = request.args.get("filter_metric")
        flexologist_name = request.args.get("flexologist_name")

        # Get user's admin_id
        user_info = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .single()
            .execute()
        )
        user_id = user_info.data["admin_id"]

        if not duration:
            return jsonify({"error": "Duration is required", "status": "error"}), 400

        # Get date range
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
            return jsonify({"error": "Invalid duration", "status": "error"}), 400

        # Get config_id
        config_result = (
            supabase.table("robot_process_automation_config")
            .select("id, excluded_flexologists")
            .eq("admin_id", user_id)
            .single()
            .execute()
        )

        if not config_result.data:
            return jsonify({"error": "No RPA config found", "status": "error"}), 400

        config_id = config_result.data["id"]
        excluded_flexologists_raw = config_result.data.get("excluded_flexologists")
        excluded_flexologists = None
        if excluded_flexologists_raw:
            try:
                excluded_flexologists = json.loads(excluded_flexologists_raw)
            except Exception:
                excluded_flexologists = None

        # Determine filter_bookings value
        filter_bookings = None
        if filter_metric == "first":
            filter_bookings = "YES"
        elif filter_metric == "subsequent":
            filter_bookings = "NO"

        # Build query dynamically - NO CODE DUPLICATION
        rpa_notes = []
        offset = 0
        limit = 1000

        while True:
            # Start building the query
            query = (
                supabase.table("robot_process_automation_notes_records")
                .select(
                    "flexologist_name, location, first_timer, note_score, "
                    "appointment_date, note_oppurtunities"
                )
                .eq("config_id", config_id)
                .neq("status", "No Show")
                .gte("appointment_date", start_date)
                .lt("appointment_date", end_date)
            )

            # Apply exclusion filter only when we have a valid list
            if excluded_flexologists:
                query = query.not_.in_("flexologist_name", excluded_flexologists)

            # Add optional filters
            if filter_bookings:
                query = query.eq("first_timer", filter_bookings)
            if location:
                query = query.eq("location", location)
            if flexologist_name:
                query = query.eq("flexologist_name", flexologist_name)

            # Execute with pagination
            data = query.range(offset, offset + limit - 1).execute().data
            rpa_notes.extend(data)

            if len(data) < limit:
                break
            offset += limit

        # Early return if no notes
        if not rpa_notes:
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "No RPA notes found",
                        "note_opportunities": [],
                        "total_quality_notes": 0,
                        "total_notes": 0,
                        "total_notes_with_opportunities": 0,
                        "location": [],
                        "flexologist": [],
                    }
                ),
                200,
            )

        # Use defaultdict for cleaner counting
        from collections import defaultdict

        locations_with_notes_count = defaultdict(int)
        flexologist_with_notes_count = defaultdict(int)
        locations_with_opportunity_count = defaultdict(int)
        flexologist_with_opportunity_count = defaultdict(int)
        flexologist_notes_percentage_obj = defaultdict(
            lambda: {"percentage": 0, "total": 0}
        )
        location_notes_percentage_obj = defaultdict(
            lambda: {"percentage": 0, "total": 0}
        )

        # Opportunity mapping for backward compatibility
        opportunity_mapping = {
            "Session Note: Problem Presented": "Problem Presented",
            "Session Note: What was worked On": "Current Session Activity",
            "Session Note: Tension Level & Frequency": "Current Session Activity",
            "Session Note: Prescribed Action": "Next Session Focus",
            "Session Note: Homework": "Homework",
        }

        # Define opportunities based on filter_metric
        if filter_metric in ["first", "all"]:
            opportunities = [
                "Confirmation Call",
                "Grip Sock Notice",
                "Arrive Early",
                "Location",
                "Prepaid",
                "Keynote",
                "Stated Goal",
                "Emotional Why",
                "Prior Solutions",
                "Routine Captured",
                "Physical/Medical Issue",
                "Plan Recommendation",
                "Problem Presented",
                "Current Session Activity",
                "Next Session Focus",
                "Homework",
            ]
        else:
            opportunities = [
                "Problem Presented",
                "Current Session Activity",
                "Next Session Focus",
                "Homework",
            ]

        opportunities_count = {opp: 0 for opp in opportunities}
        notes_with_opportunities = []
        total_quality_notes_percentage_array = []

        # Single pass through all notes
        for note in rpa_notes:
            location_key = note["location"]
            flexologist_key = note["flexologist_name"].lower()

            # Count by location and flexologist
            locations_with_notes_count[location_key] += 1
            flexologist_with_notes_count[flexologist_key] += 1

            # Calculate quality percentage
            if note["first_timer"] == "YES":
                max_score = 18
            else:
                max_score = 4

            if note["note_score"] == "N/A":
                percentage = 0
            else:
                percentage = (int(note["note_score"]) * 100) / max_score

            total_quality_notes_percentage_array.append(percentage)
            flexologist_notes_percentage_obj[note["flexologist_name"]][
                "percentage"
            ] += percentage
            flexologist_notes_percentage_obj[note["flexologist_name"]]["total"] += 1
            location_notes_percentage_obj[location_key]["percentage"] += percentage
            location_notes_percentage_obj[location_key]["total"] += 1

            # Process opportunities
            note_opps = note["note_oppurtunities"]
            has_opportunities = note_opps and note_opps not in ["N/A", "[]", "", []]

            if has_opportunities:
                notes_with_opportunities.append(note)
                locations_with_opportunity_count[location_key] += 1
                flexologist_with_opportunity_count[flexologist_key] += 1

                # Parse and count opportunities
                try:
                    lowered_opps = [
                        item.lower()
                        for item in json.loads(note_opps)
                        if isinstance(item, str)
                    ]

                    for opportunity in opportunities:
                        opp_lower = opportunity.lower()
                        # Check new opportunity name
                        if opp_lower in lowered_opps:
                            opportunities_count[opportunity] += 1
                        else:
                            # Check old opportunity names
                            old_names = [
                                old.lower()
                                for old, new in opportunity_mapping.items()
                                if new.lower() == opp_lower
                            ]
                            if any(old_name in lowered_opps for old_name in old_names):
                                opportunities_count[opportunity] += 1
                except (json.JSONDecodeError, TypeError):
                    continue

        # Calculate percentages
        total_notes = len(rpa_notes)

        # Opportunity percentages
        for opportunity in opportunities:
            opportunities_count[opportunity] = round(
                (opportunities_count[opportunity] / total_notes) * 100, 2
            )

        # Location opportunity percentages
        opportunities_count_with_location = {}
        for location_key in locations_with_notes_count:
            if location_key in locations_with_opportunity_count:
                opportunities_count_with_location[location_key] = round(
                    (
                        locations_with_opportunity_count[location_key]
                        / locations_with_notes_count[location_key]
                    )
                    * 100,
                    2,
                )
            else:
                opportunities_count_with_location[location_key] = 0

        # Flexologist opportunity percentages
        for flexologist_key in flexologist_with_notes_count:
            if flexologist_key in flexologist_with_opportunity_count:
                flexologist_with_opportunity_count[flexologist_key] = round(
                    (
                        flexologist_with_opportunity_count[flexologist_key]
                        / flexologist_with_notes_count[flexologist_key]
                    )
                    * 100,
                    2,
                )
            else:
                flexologist_with_opportunity_count[flexologist_key] = 0

        # Sort results
        sorted_opportunities = sorted(
            opportunities_count.items(), key=lambda item: item[1], reverse=True
        )

        sorted_location_notes = sorted(
            location_notes_percentage_obj.items(),
            key=lambda item: (
                item[1]["percentage"] / item[1]["total"] if item[1]["total"] > 0 else 0
            ),
            reverse=True,
        )

        sorted_flexologist_notes = sorted(
            flexologist_notes_percentage_obj.items(),
            key=lambda item: (
                item[1]["percentage"] / item[1]["total"] if item[1]["total"] > 0 else 0
            ),
            reverse=True,
        )

        # Calculate total quality percentage
        total_quality_notes_percentage = (
            sum(total_quality_notes_percentage_array)
            / len(total_quality_notes_percentage_array)
            if total_quality_notes_percentage_array
            else 0
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "note_opportunities": [
                        {"opportunity": opp, "percentage": pct}
                        for opp, pct in sorted_opportunities
                    ],
                    "total_quality_notes": total_notes,
                    "total_quality_notes_percentage": round(
                        total_quality_notes_percentage
                    ),
                    "total_notes": total_notes,
                    "total_notes_with_opportunities": len(notes_with_opportunities),
                    "total_notes_with_opportunities_percentage": round(
                        (len(notes_with_opportunities) / total_notes) * 100, 2
                    ),
                    "location": [
                        {
                            "location": loc,
                            "percentage": (
                                round(data["percentage"] / data["total"], 2)
                                if data["total"] > 0
                                else 0
                            ),
                        }
                        for loc, data in sorted_location_notes
                    ],
                    "flexologist": [
                        {
                            "flexologist": flex,
                            "percentage": (
                                round(data["percentage"] / data["total"], 2)
                                if data["total"] > 0
                                else 0
                            ),
                        }
                        for flex, data in sorted_flexologist_notes
                    ],
                }
            ),
            200,
        )

    except Exception as e:
        logging.error(f"Error in POST api/admin/analytics/rpa_audit: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get_rpa_audit_details", methods=["POST"])
@require_bearer_token
def get_rpa_audit_details(token):
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

        data = request.json
        opportunity = data["opportunity"]
        duration = data["duration"]
        location = data.get("location")
        flexologist_name = data.get("flexologist_name")

        # Get date range
        if duration == "custom":
            start_date_str = data["start_date"]
            end_date_str = data["end_date"]
            start_date, end_date = get_start_and_end_date(
                duration, start_date_str, end_date_str
            )
        else:
            start_date, end_date = get_start_and_end_date(duration)

        if not start_date or not end_date:
            return jsonify({"error": "Invalid duration", "status": "error"}), 400

        # Get config_id
        config_result = (
            supabase.table("robot_process_automation_config")
            .select("id, excluded_flexologists")
            .eq("admin_id", user_id)
            .single()
            .execute()
        )

        if not config_result.data:
            return jsonify({"error": "No RPA config found", "status": "error"}), 400

        config_id = config_result.data["id"]

        excluded_flexologists_raw = config_result.data.get("excluded_flexologists")
        excluded_flexologists = None
        if excluded_flexologists_raw:
            try:
                excluded_flexologists = json.loads(excluded_flexologists_raw)
            except Exception:
                excluded_flexologists = None

        # Build query dynamically
        rpa_notes = []
        offset = 0
        limit = 1000

        while True:
            # Build query with optional filters
            query = (
                supabase.table("robot_process_automation_notes_records")
                .select(
                    "flexologist_name, location, first_timer, note_score, "
                    "appointment_date, note_oppurtunities"
                )
                .eq("config_id", config_id)
                .neq("status", "No Show")
                .gte("appointment_date", start_date)
                .lt("appointment_date", end_date)
            )

            # Apply exclusion filter only when we have a valid list
            if excluded_flexologists:
                query = query.not_.in_("flexologist_name", excluded_flexologists)

            # Add optional filters
            if location:
                query = query.eq("location", location)
            if flexologist_name:
                query = query.eq("flexologist_name", flexologist_name)

            # Execute with pagination
            data_batch = query.range(offset, offset + limit - 1).execute().data
            rpa_notes.extend(data_batch)

            if len(data_batch) < limit:
                break
            offset += limit

        # Early return if no notes
        if not rpa_notes:
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "No RPA notes found",
                        "location": [],
                        "flexologist": [],
                    }
                ),
                200,
            )

        # Opportunity mapping for backward compatibility
        opportunity_mapping = {
            "Session Note: Problem Presented": "Problem Presented",
            "Session Note: What was worked On": "Current Session Activity",
            "Session Note: Tension Level & Frequency": "Current Session Activity",
            "Session Note: Prescribed Action": "Next Session Focus",
            "Session Note: Homework": "Homework",
        }

        # Pre-compute old names for the requested opportunity
        opportunity_lower = opportunity.lower()
        old_names = [
            old.lower()
            for old, new in opportunity_mapping.items()
            if new.lower() == opportunity_lower
        ]

        # Use defaultdict for cleaner counting
        from collections import defaultdict

        locations_with_opportunity_count = defaultdict(int)
        flexologist_with_opportunity_count = defaultdict(int)
        total_location_notes = defaultdict(int)
        total_flexologist_notes = defaultdict(int)

        locations_with_particular_opportunity_count = defaultdict(int)
        flexologist_with_particular_opportunity_count = defaultdict(int)

        # Quality score tracking
        location_quality_scores = defaultdict(list)
        flexologist_quality_scores = defaultdict(list)

        # Single pass through all notes
        for note in rpa_notes:
            location_key = note["location"]
            flexologist_key = note["flexologist_name"].lower()
            flexologist_display_key = note["flexologist_name"]

            # Count all notes by location and flexologist
            total_location_notes[location_key] += 1
            total_flexologist_notes[flexologist_display_key] += 1

            # Calculate quality score
            max_score = 18 if note["first_timer"] == "YES" else 4
            if note["note_score"] == "N/A":
                percentage = 0
            else:
                percentage = (int(note["note_score"]) * 100) / max_score

            location_quality_scores[location_key].append(percentage)
            flexologist_quality_scores[flexologist_display_key].append(percentage)

            # Check if note has opportunities
            note_opps = note["note_oppurtunities"]
            has_opportunities = note_opps and note_opps not in ["N/A", "[]", "", []]

            if has_opportunities:
                locations_with_opportunity_count[location_key] += 1
                flexologist_with_opportunity_count[flexologist_key] += 1

                # Parse opportunities and check for the specific one
                try:
                    lowered_opps = [
                        item.lower()
                        for item in json.loads(note_opps)
                        if isinstance(item, str)
                    ]

                    # Check if requested opportunity is present (new name or old names)
                    opportunity_found = opportunity_lower in lowered_opps or any(
                        old_name in lowered_opps for old_name in old_names
                    )

                    if opportunity_found:
                        locations_with_particular_opportunity_count[location_key] += 1
                        flexologist_with_particular_opportunity_count[
                            flexologist_key
                        ] += 1

                except (json.JSONDecodeError, TypeError):
                    continue

        # Calculate percentages for locations
        location_results = []
        for location_key in locations_with_opportunity_count:
            particular_count = locations_with_particular_opportunity_count.get(
                location_key, 0
            )
            opportunity_count = locations_with_opportunity_count[location_key]
            total_count = total_location_notes[location_key]

            if opportunity_count > 0:
                percentage = round((particular_count / opportunity_count) * 100, 2)
            else:
                percentage = 0

            percentage_note_quality = (
                round((particular_count / total_count) * 100, 2)
                if total_count > 0
                else 0
            )

            location_results.append(
                {
                    "location": location_key,
                    "percentage": percentage,
                    "particular_count": particular_count,
                    "total_count": total_count,
                    "percentage_note_quality": percentage_note_quality,
                }
            )

        # Sort locations by percentage
        location_results.sort(key=lambda x: x["percentage"], reverse=True)

        # Calculate percentages for flexologists
        flexologist_results = []
        for flexologist_key in flexologist_with_opportunity_count:
            particular_count = flexologist_with_particular_opportunity_count.get(
                flexologist_key, 0
            )
            opportunity_count = flexologist_with_opportunity_count[flexologist_key]

            # Find the display name (with proper casing)
            flexologist_display_name = None
            for note in rpa_notes:
                if note["flexologist_name"].lower() == flexologist_key:
                    flexologist_display_name = note["flexologist_name"]
                    break

            total_count = total_flexologist_notes.get(flexologist_display_name, 0)

            if opportunity_count > 0:
                percentage = round((particular_count / opportunity_count) * 100, 2)
            else:
                percentage = 0

            percentage_note_quality = (
                round((particular_count / total_count) * 100, 2)
                if total_count > 0
                else 0
            )

            flexologist_results.append(
                {
                    "flexologist": flexologist_key,
                    "percentage": percentage,
                    "particular_count": particular_count,
                    "total_count": total_count,
                    "percentage_note_quality": percentage_note_quality,
                }
            )

        # Sort flexologists by percentage
        flexologist_results.sort(key=lambda x: x["percentage"], reverse=True)

        return (
            jsonify(
                {
                    "status": "success",
                    "location": location_results,
                    "flexologist": flexologist_results,
                }
            ),
            200,
        )

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/analytics/get_rpa_audit_details: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get_ranking_analytics", methods=["POST"])
@require_bearer_token
def get_ranking_analytics(token):
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

        data = request.json
        metric = data.get("metric", "total_visits")
        filter_metric = data.get("filter_metric", "all")
        duration = data["duration"]

        # Get date range
        if duration == "custom":
            start_date_str = data["start_date"]
            end_date_str = data["end_date"]
            start_date, end_date = get_start_and_end_date(
                duration, start_date_str, end_date_str
            )
        else:
            start_date, end_date = get_start_and_end_date(duration)

        if not start_date or not end_date:
            return jsonify({"error": "Invalid duration", "status": "error"}), 400

        # Get config_id
        config_result = (
            supabase.table("robot_process_automation_config")
            .select("id, excluded_flexologists")
            .eq("admin_id", user_id)
            .single()
            .execute()
        )

        if not config_result.data:
            return jsonify({"error": "No RPA config found", "status": "error"}), 400

        config_id = config_result.data["id"]
        excluded_flexologists_raw = config_result.data.get("excluded_flexologists")
        excluded_flexologists = None
        if excluded_flexologists_raw:
            try:
                excluded_flexologists = json.loads(excluded_flexologists_raw)
            except Exception:
                excluded_flexologists = None

        # ===== METRIC: total_client_visits =====
        if metric == "total_client_visits":
            # Determine filter
            first_timer_filter = None
            if filter_metric == "first":
                first_timer_filter = "YES"
            elif filter_metric == "subsequent":
                first_timer_filter = "NO"

            # Fetch notes with dynamic query
            rpa_notes = []
            offset = 0
            limit = 1000

            while True:
                query = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("flexologist_name, location")
                    .eq("config_id", config_id)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                )

                # Apply exclusion filter only when we have a valid list
                if excluded_flexologists:
                    query = query.not_.in_("flexologist_name", excluded_flexologists)

                if first_timer_filter:
                    query = query.eq("first_timer", first_timer_filter)

                data_batch = query.range(offset, offset + limit - 1).execute().data
                rpa_notes.extend(data_batch)

                if len(data_batch) < limit:
                    break
                offset += limit

            if not rpa_notes:
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "No notes found",
                            "data": [],
                            "data_flex": [],
                            "metric": metric,
                        }
                    ),
                    200,
                )

            # Count by location and flexologist
            from collections import defaultdict

            count_location = defaultdict(int)
            count_flex = defaultdict(int)

            for note in rpa_notes:
                count_location[note["location"]] += 1
                count_flex[note["flexologist_name"]] += 1

            # Sort and format
            sorted_locations = sorted(
                count_location.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            sorted_flex = sorted(
                count_flex.items(),
                key=lambda item: item[1],
                reverse=True,
            )

            total_notes = len(rpa_notes)

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": [
                            {"name": name, "count": count, "total": total_notes}
                            for name, count in sorted_locations
                        ],
                        "data_flex": [
                            {"name": name, "count": count, "total": total_notes}
                            for name, count in sorted_flex
                        ],
                        "metric": metric,
                    }
                ),
                200,
            )

        # ===== METRIC: percentage_app_submission =====
        if metric == "percentage_app_submission":
            # Fetch all RPA notes
            all_notes = []
            offset = 0
            limit = 1000

            while True:
                # Build the base query
                query = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("location, flexologist_name")
                    .eq("config_id", config_id)
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .neq("status", "No Show")
                )

                # Apply exclusion filter only when we have a valid list
                if excluded_flexologists:
                    query = query.not_.in_("flexologist_name", excluded_flexologists)

                data_batch = query.range(offset, offset + limit - 1).execute().data

                all_notes.extend(data_batch)

                if len(data_batch) < limit:
                    break
                offset += limit

            if not all_notes:
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "No notes found",
                            "data": [],
                            "data_flex": [],
                            "metric": metric,
                        }
                    ),
                    200,
                )

            # Get all flexologists
            flexologists = (
                supabase.table("users")
                .select("id")
                .eq("admin_id", user_id)
                .eq("role_id", 3)
                .or_(f"disabled_at.is.null,disabled_at.gte.{start_date}")
                .execute()
            ).data

            if not flexologists:
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "No flexologists found",
                            "data": [],
                            "data_flex": [],
                            "metric": metric,
                        }
                    ),
                    200,
                )

            # Fetch ALL app submissions in ONE query (instead of N queries)
            flexologist_ids = [f["id"] for f in flexologists]
            app_submitted = []
            offset = 0
            limit = 1000

            while True:
                submitted_batch = (
                    supabase.table("clubready_bookings")
                    .select("location, flexologist_name")
                    .in_("user_id", flexologist_ids)
                    .eq("submitted", True)
                    .gte("created_at", start_date)
                    .lt("created_at", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                app_submitted.extend(submitted_batch)

                if len(submitted_batch) < limit:
                    break
                offset += limit

            # Count visits and submissions
            from collections import defaultdict

            total_visits_per_location = defaultdict(int)
            total_visits_per_flex = defaultdict(int)
            submitted_per_location = defaultdict(int)
            submitted_per_flex = defaultdict(int)

            for note in all_notes:
                loc = note["location"]
                flex = (
                    note["flexologist_name"].lower()
                    if note.get("flexologist_name")
                    else ""
                )
                total_visits_per_location[loc] += 1
                total_visits_per_flex[flex] += 1

            for sub in app_submitted:
                loc = sub["location"].lower()
                flex = (
                    sub["flexologist_name"].lower()
                    if sub.get("flexologist_name")
                    else ""
                )
                submitted_per_location[loc] += 1
                submitted_per_flex[flex] += 1

            # Calculate percentages
            location_percentages = {}
            for loc in total_visits_per_location:
                sub = submitted_per_location.get(loc, 0)
                total = total_visits_per_location[loc]
                pct = round((sub / total) * 100, 2) if total > 0 else 0
                location_percentages[loc] = {"pct": pct, "total": total}

            flex_percentages = {}
            for flex in total_visits_per_flex:
                sub = submitted_per_flex.get(flex, 0)
                total = total_visits_per_flex[flex]
                pct = round((sub / total) * 100, 2) if total > 0 else 0
                flex_percentages[flex] = {"pct": pct, "total": total}

            # Sort results
            sorted_locations = sorted(
                location_percentages.items(),
                key=lambda item: item[1]["pct"],
                reverse=True,
            )
            sorted_flex = sorted(
                flex_percentages.items(),
                key=lambda item: item[1]["pct"],
                reverse=True,
            )

            # Calculate overall percentage
            total_robot_bookings = len(all_notes)
            total_app_submitted = len(app_submitted)
            overall_percentage = round(
                (
                    (total_app_submitted / total_robot_bookings * 100)
                    if total_robot_bookings > 0
                    else 0
                ),
                2,
            )

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": [
                            {
                                "name": loc,
                                "count": data_dict["pct"],
                                "total": data_dict["total"],
                            }
                            for loc, data_dict in sorted_locations
                        ],
                        "data_flex": [
                            {
                                "name": flex,
                                "count": data_dict["pct"],
                                "total": data_dict["total"],
                            }
                            for flex, data_dict in sorted_flex
                        ],
                        "metric": metric,
                        "overall_percentage": overall_percentage,
                    }
                ),
                200,
            )

        # ===== METRIC: note_quality_percentage =====
        if metric == "note_quality_percentage":
            # Determine filter
            first_timer_filter = None
            if filter_metric == "first":
                first_timer_filter = "YES"
            elif filter_metric == "subsequent":
                first_timer_filter = "NO"

            # Fetch notes
            all_notes = []
            offset = 0
            limit = 1000

            while True:
                query = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("location, flexologist_name, note_score, first_timer")
                    .eq("config_id", config_id)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                )

                # Apply exclusion filter only when we have a valid list
                if excluded_flexologists:
                    query = query.not_.in_("flexologist_name", excluded_flexologists)

                if first_timer_filter:
                    query = query.eq("first_timer", first_timer_filter)

                data_batch = query.range(offset, offset + limit - 1).execute().data
                all_notes.extend(data_batch)

                if len(data_batch) < limit:
                    break
                offset += limit

            if not all_notes:
                return (
                    jsonify(
                        {
                            "status": "success",
                            "data": [],
                            "data_flex": [],
                            "metric": metric,
                        }
                    ),
                    200,
                )

            # Calculate averages
            from collections import defaultdict

            group_sums_location = defaultdict(float)
            group_counts_location = defaultdict(int)
            group_sums_flex = defaultdict(float)
            group_counts_flex = defaultdict(int)

            for booking in all_notes:
                score = (
                    int(booking["note_score"]) if booking["note_score"] != "N/A" else 0
                )
                max_score = 16.0 if booking["first_timer"] == "YES" else 4.0
                percentage = (score / max_score) * 100

                loc = booking["location"].lower()
                flex = booking["flexologist_name"].lower()

                group_sums_location[loc] += percentage
                group_counts_location[loc] += 1
                group_sums_flex[flex] += percentage
                group_counts_flex[flex] += 1

            # Calculate and sort averages
            averages_location = {
                key: {
                    "avg": round(
                        group_sums_location[key] / group_counts_location[key], 2
                    ),
                    "total": group_counts_location[key],
                }
                for key in group_sums_location
            }

            averages_flex = {
                key: {
                    "avg": round(group_sums_flex[key] / group_counts_flex[key], 2),
                    "total": group_counts_flex[key],
                }
                for key in group_sums_flex
            }

            sorted_locations = sorted(
                averages_location.items(),
                key=lambda item: item[1]["avg"],
                reverse=True,
            )
            sorted_flex = sorted(
                averages_flex.items(),
                key=lambda item: item[1]["avg"],
                reverse=True,
            )

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": [
                            {
                                "name": name,
                                "count": data_dict["avg"],
                                "total": data_dict["total"],
                            }
                            for name, data_dict in sorted_locations
                        ],
                        "data_flex": [
                            {
                                "name": name,
                                "count": data_dict["avg"],
                                "total": data_dict["total"],
                            }
                            for name, data_dict in sorted_flex
                        ],
                        "metric": metric,
                    }
                ),
                200,
            )

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/analytics/get_ranking_analytics: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get_location_analytics", methods=["POST"])
@require_bearer_token
def get_location_analytics(token):
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

        data = request.json
        location = data.get("location")

        if not location:
            return jsonify({"error": "Location is required", "status": "error"}), 400

        metric = data.get("metric", "total_visits")
        filter_metric = data.get("filter_metric", "all")
        duration = data["duration"]

        # Get date range
        if duration == "custom":
            start_date_str = data["start_date"]
            end_date_str = data["end_date"]
            start_date, end_date = get_start_and_end_date(
                duration, start_date_str, end_date_str
            )
        else:
            start_date, end_date = get_start_and_end_date(duration)

        if not start_date or not end_date:
            return jsonify({"error": "Invalid duration", "status": "error"}), 400

        # Get config_id
        config_result = (
            supabase.table("robot_process_automation_config")
            .select("id, excluded_flexologists")
            .eq("admin_id", user_id)
            .single()
            .execute()
        )

        if not config_result.data:
            return jsonify({"error": "No RPA config found", "status": "error"}), 400

        config_id = config_result.data["id"]
        excluded_flexologists_raw = config_result.data.get("excluded_flexologists")
        excluded_flexologists = None
        if excluded_flexologists_raw:
            try:
                excluded_flexologists = json.loads(excluded_flexologists_raw)
            except Exception:
                excluded_flexologists = None

        # ===== METRIC: total_client_visits =====
        if metric == "total_client_visits":
            # Determine filter
            first_timer_filter = None
            if filter_metric == "first":
                first_timer_filter = "YES"
            elif filter_metric == "subsequent":
                first_timer_filter = "NO"

            # Fetch notes with dynamic query - only select needed fields
            rpa_notes = []
            offset = 0
            limit = 1000

            while True:
                query = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("flexologist_name")
                    .eq("config_id", config_id)
                    .eq("location", location)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                )
                if excluded_flexologists:
                    query = query.not_.in_("flexologist_name", excluded_flexologists)

                if first_timer_filter:
                    query = query.eq("first_timer", first_timer_filter)

                data_batch = query.range(offset, offset + limit - 1).execute().data
                rpa_notes.extend(data_batch)

                if len(data_batch) < limit:
                    break
                offset += limit

            if not rpa_notes:
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "No notes found",
                            "data": [],
                            "metric": metric,
                        }
                    ),
                    200,
                )

            # Count by flexologist
            from collections import defaultdict

            count_flex = defaultdict(int)

            for note in rpa_notes:
                count_flex[note["flexologist_name"]] += 1

            # Sort and format
            sorted_flex = sorted(
                count_flex.items(),
                key=lambda item: item[1],
                reverse=True,
            )

            total_notes = len(rpa_notes)

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": [
                            {"name": name, "count": count, "total": total_notes}
                            for name, count in sorted_flex
                        ],
                        "metric": metric,
                    }
                ),
                200,
            )

        # ===== METRIC: percentage_app_submission =====
        if metric == "percentage_app_submission":
            # Fetch all RPA notes for this location
            all_notes = []
            offset = 0
            limit = 1000

            while True:
                # Build the base query
                query = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("flexologist_name")
                    .eq("config_id", config_id)
                    .eq("location", location)
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .neq("status", "No Show")
                )

                # Apply exclusion filter only when we have a valid list
                if excluded_flexologists:
                    query = query.not_.in_("flexologist_name", excluded_flexologists)

                data_batch = query.range(offset, offset + limit - 1).execute().data

                all_notes.extend(data_batch)

                if len(data_batch) < limit:
                    break
                offset += limit

            if not all_notes:
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "No notes found",
                            "data": [],
                            "metric": metric,
                        }
                    ),
                    200,
                )

            # Get all flexologists
            flexologists = (
                supabase.table("users")
                .select("id")
                .eq("admin_id", user_id)
                .eq("role_id", 3)
                .or_(f"disabled_at.is.null,disabled_at.gte.{start_date}")
                .execute()
            ).data

            if not flexologists:
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "No flexologists found",
                            "data": [],
                            "metric": metric,
                        }
                    ),
                    200,
                )

            # Fetch ALL app submissions in ONE query (instead of N queries)
            flexologist_ids = [f["id"] for f in flexologists]
            app_submitted = []
            offset = 0
            limit = 1000

            while True:
                # Build the base query
                query = (
                    supabase.table("clubready_bookings")
                    .select("flexologist_name")
                    .in_("user_id", flexologist_ids)
                    .eq("location", location)
                    .eq("submitted", True)
                    .gte("created_at", start_date)
                    .lt("created_at", end_date)
                )

                # Apply exclusion filter only when we have a valid list
                if excluded_flexologists:
                    query = query.not_.in_("flexologist_name", excluded_flexologists)

                submitted_batch = query.range(offset, offset + limit - 1).execute().data
                app_submitted.extend(submitted_batch)

                if len(submitted_batch) < limit:
                    break
                offset += limit

            # Count visits and submissions
            from collections import defaultdict

            total_visits_per_flex = defaultdict(int)
            submitted_per_flex = defaultdict(int)

            for note in all_notes:
                flex = (
                    note["flexologist_name"].lower()
                    if note.get("flexologist_name")
                    else ""
                )
                total_visits_per_flex[flex] += 1

            for sub in app_submitted:
                flex = (
                    sub["flexologist_name"].lower()
                    if sub.get("flexologist_name")
                    else ""
                )
                submitted_per_flex[flex] += 1

            # Calculate percentages
            flex_percentages = {}
            for flex in total_visits_per_flex:
                sub = submitted_per_flex.get(flex, 0)
                total = total_visits_per_flex[flex]
                pct = round((sub / total) * 100, 2) if total > 0 else 0
                flex_percentages[flex] = {"pct": pct, "total": total}

            # Sort results
            sorted_flex = sorted(
                flex_percentages.items(),
                key=lambda item: item[1]["pct"],
                reverse=True,
            )

            # Calculate overall percentage
            total_robot_bookings = len(all_notes)
            total_app_submitted = len(app_submitted)
            overall_percentage = round(
                (
                    (total_app_submitted / total_robot_bookings * 100)
                    if total_robot_bookings > 0
                    else 0
                ),
                2,
            )

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": [
                            {
                                "name": flex,
                                "count": data_dict["pct"],
                                "total": data_dict["total"],
                            }
                            for flex, data_dict in sorted_flex
                        ],
                        "metric": metric,
                        "overall_percentage": overall_percentage,
                    }
                ),
                200,
            )

        # ===== METRIC: note_quality_percentage =====
        if metric == "note_quality_percentage":
            # Determine filter
            first_timer_filter = None
            if filter_metric == "first":
                first_timer_filter = "YES"
            elif filter_metric == "subsequent":
                first_timer_filter = "NO"

            # Fetch notes
            all_notes = []
            offset = 0
            limit = 1000

            while True:
                query = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("flexologist_name, note_score, first_timer")
                    .eq("config_id", config_id)
                    .eq("location", location)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                )
                if excluded_flexologists:
                    query = query.not_.in_("flexologist_name", excluded_flexologists)

                if first_timer_filter:
                    query = query.eq("first_timer", first_timer_filter)

                data_batch = query.range(offset, offset + limit - 1).execute().data
                all_notes.extend(data_batch)

                if len(data_batch) < limit:
                    break
                offset += limit

            if not all_notes:
                return (
                    jsonify(
                        {
                            "status": "success",
                            "data": [],
                            "metric": metric,
                        }
                    ),
                    200,
                )

            # Calculate averages
            from collections import defaultdict

            group_sums_flex = defaultdict(float)
            group_counts_flex = defaultdict(int)

            for booking in all_notes:
                score = (
                    int(booking["note_score"]) if booking["note_score"] != "N/A" else 0
                )
                max_score = 16.0 if booking["first_timer"] == "YES" else 4.0
                percentage = (score / max_score) * 100

                flex = booking["flexologist_name"].lower()

                group_sums_flex[flex] += percentage
                group_counts_flex[flex] += 1

            # Calculate and sort averages
            averages_flex = {
                key: {
                    "avg": round(group_sums_flex[key] / group_counts_flex[key], 2),
                    "total": group_counts_flex[key],
                }
                for key in group_sums_flex
            }

            sorted_flex = sorted(
                averages_flex.items(),
                key=lambda item: item[1]["avg"],
                reverse=True,
            )

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": [
                            {
                                "name": name,
                                "count": data_dict["avg"],
                                "total": data_dict["total"],
                            }
                            for name, data_dict in sorted_flex
                        ],
                        "metric": metric,
                    }
                ),
                200,
            )

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/analytics/get_location_analytics: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


def init_analytics_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/admin/analytics")
