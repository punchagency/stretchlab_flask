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
        user_id = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .execute()
        ).data[0]["admin_id"]

        if not duration:
            return jsonify({"error": "Duration is required", "status": "error"}), 400
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

        config_id = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", user_id)
            .execute()
        ).data

        if not config_id:
            return jsonify({"error": "No RPA config found", "status": "error"}), 400

        filter_bookings = None

        if filter_metric == "first":
            filter_bookings = "YES"

        if filter_metric == "subsequent":
            filter_bookings = "NO"

        config_id = config_id[0]["id"]
        rpa_notes = []
        offset = 0
        limit = 1000
        if not location and not flexologist_name:
            while True:
                if filter_bookings:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("first_timer", filter_bookings)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                else:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                rpa_notes.extend(data)
                if len(data) < limit:
                    break
                offset += limit

        if location and not flexologist_name:

            while True:
                if filter_bookings:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("location", location)
                        .eq("first_timer", filter_bookings)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                else:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("location", location)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                rpa_notes.extend(data)
                if len(data) < limit:
                    break
                offset += limit

        if flexologist_name and not location:
            while True:
                if filter_bookings:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("flexologist_name", flexologist_name)
                        .eq("first_timer", filter_bookings)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                else:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("flexologist_name", flexologist_name)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                rpa_notes.extend(data)
                if len(data) < limit:
                    break
                offset += limit

        if location and flexologist_name:
            while True:
                if filter_bookings:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("location", location)
                        .eq("flexologist_name", flexologist_name)
                        .eq("first_timer", filter_bookings)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                else:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("location", location)
                        .eq("flexologist_name", flexologist_name)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                rpa_notes.extend(data)
                if len(data) < limit:
                    break
                offset += limit

        if not rpa_notes or len(rpa_notes) == 0:
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

        locations_with_notes_count = {}
        flexologist_with_notes_count = {}
        for note in rpa_notes:
            if note["location"] not in locations_with_notes_count:
                locations_with_notes_count[note["location"]] = 0
            locations_with_notes_count[note["location"]] += 1
            if note["flexologist_name"].lower() not in flexologist_with_notes_count:
                flexologist_with_notes_count[note["flexologist_name"].lower()] = 0
            flexologist_with_notes_count[note["flexologist_name"].lower()] += 1

        locations_with_notes_count = dict(
            sorted(
                locations_with_notes_count.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )

        flexologist_with_notes_count = dict(
            sorted(
                flexologist_with_notes_count.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )

        # Hard coding for now would be better if i add it to the db
        if filter_metric in ["first", "all"]:
            opportunities = [
                "Needs Analysis: Deep Emotional Reason(Why)",
                "Needs Analysis: Physiscal Need",
                "Session Note: Problem Presented",
                "Session Note: What was worked On",
                "Session Note: Tension Level & Frequency",
                "Session Note: Prescribed Action",
                "Session Note: Homework",
                "Quality: No Future Bookings",
                "Quality: Missing Homework",
                "Quality: Missing Waiver",
                "Quality: Other",
            ]
        else:
            opportunities = [
                "Session Note: Problem Presented",
                "Session Note: What was worked On",
                "Session Note: Tension Level & Frequency",
                "Session Note: Prescribed Action",
                "Session Note: Homework",
            ]

        notes_with_opportunities = []
        locations_with_opportunity_count = {}
        flexologist_with_opportunity_count = {}

        for note in rpa_notes:
            if (
                note["note_oppurtunities"] != "N/A"
                and note["note_oppurtunities"] != "[]"
                and note["note_oppurtunities"] != ""
                and note["note_oppurtunities"] != []
                and note["note_oppurtunities"] != None
            ):
                notes_with_opportunities.append(note)
                if note["location"] not in locations_with_opportunity_count:
                    locations_with_opportunity_count[note["location"]] = 0
                locations_with_opportunity_count[note["location"]] += 1
                if (
                    note["flexologist_name"].lower()
                    not in flexologist_with_opportunity_count
                ):
                    flexologist_with_opportunity_count[
                        note["flexologist_name"].lower()
                    ] = 0
                flexologist_with_opportunity_count[
                    note["flexologist_name"].lower()
                ] += 1

        opportunities_count = {}

        for opportunity in opportunities:
            opportunities_count[opportunity] = 0

        for note in notes_with_opportunities:
            lowered_opps = [
                item.lower()
                for item in json.loads(note["note_oppurtunities"])
                if isinstance(item, str)
            ]

            for opportunity in opportunities:
                if opportunity.lower() in lowered_opps:
                    opportunities_count[opportunity] += 1

        for opportunity in opportunities:
            opportunities_count[opportunity] = round(
                (opportunities_count[opportunity] / len(rpa_notes)) * 100,
                2,
            )

        opportunities_count_with_location = {}
        for location in locations_with_notes_count:
            if location in locations_with_opportunity_count:
                opportunities_count_with_location[location] = round(
                    (
                        locations_with_opportunity_count[location]
                        / locations_with_notes_count[location]
                    )
                    * 100,
                    2,
                )
            else:
                opportunities_count_with_location[location] = 0

        for flexologist in flexologist_with_notes_count:
            if flexologist in flexologist_with_opportunity_count:
                flexologist_with_opportunity_count[flexologist] = round(
                    (
                        flexologist_with_opportunity_count[flexologist]
                        / flexologist_with_notes_count[flexologist]
                    )
                    * 100,
                    2,
                )
            else:
                flexologist_with_opportunity_count[flexologist] = 0

        flexologist_with_opportunity_count = dict(
            sorted(
                flexologist_with_opportunity_count.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )

        sorted_opportunities_count_with_location = sorted(
            opportunities_count_with_location.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        sorted_flexologist_with_opportunity_count = sorted(
            flexologist_with_opportunity_count.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        opportunities_count = dict(
            sorted(opportunities_count.items(), key=lambda item: item[1], reverse=True)
        )

        total_quality_notes = len(rpa_notes) - len(notes_with_opportunities)

        sorted_opportunities = sorted(
            opportunities_count.items(), key=lambda item: item[1], reverse=True
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "note_opportunities": [
                        {"opportunity": opp, "percentage": pct}
                        for opp, pct in sorted_opportunities
                    ],
                    "total_quality_notes": total_quality_notes,
                    "total_quality_notes_percentage": round(
                        (total_quality_notes / len(rpa_notes)) * 100, 2
                    ),
                    "total_notes": len(rpa_notes),
                    "total_notes_with_opportunities": len(notes_with_opportunities),
                    "total_notes_with_opportunities_percentage": round(
                        (len(notes_with_opportunities) / len(rpa_notes)) * 100, 2
                    ),
                    "location": [
                        {"location": location, "percentage": round(100 - percentage, 2)}
                        for location, percentage in sorted_opportunities_count_with_location
                    ],
                    "flexologist": [
                        {
                            "flexologist": flexologist,
                            "percentage": round(100 - percentage, 2),
                        }
                        for flexologist, percentage in sorted_flexologist_with_opportunity_count
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
        user_id = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .execute()
        ).data[0]["admin_id"]
        data = request.json
        opportunity = data["opportunity"]
        duration = data["duration"]
        location = data.get("location", None)
        flexologist_name = data.get("flexologist_name", None)

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

        config_id = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", user_id)
            .execute()
        ).data

        if not config_id:
            return jsonify({"error": "No RPA config found", "status": "error"}), 400

        config_id = config_id[0]["id"]
        rpa_notes = []
        offset = 0
        limit = 1000
        if not location and not flexologist_name:
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                rpa_notes.extend(data)
                if len(data) < limit:
                    break
                offset += limit

        if location and not flexologist_name:
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .eq("location", location)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                rpa_notes.extend(data)
                if len(data) < limit:
                    break
                offset += limit

        if flexologist_name and not location:
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .eq("flexologist_name", flexologist_name)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                rpa_notes.extend(data)
                if len(data) < limit:
                    break
                offset += limit

        if location and flexologist_name:
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .eq("flexologist_name", flexologist_name)
                    .eq("location", location)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                rpa_notes.extend(data)
                if len(data) < limit:
                    break
                offset += limit

        if not rpa_notes or len(rpa_notes) == 0:
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

        notes_with_opportunities = []
        locations_with_opportunity_count = {}
        flexologist_with_opportunity_count = {}

        total_location_notes = {}
        total_flexologist_note = {}

        for note in rpa_notes:
            if (
                note["note_oppurtunities"] != "N/A"
                and note["note_oppurtunities"] != "[]"
                and note["note_oppurtunities"] != ""
                and note["note_oppurtunities"] != []
                and note["note_oppurtunities"] != None
            ):
                notes_with_opportunities.append(note)
                if note["location"] not in locations_with_opportunity_count:
                    locations_with_opportunity_count[note["location"]] = 0

                locations_with_opportunity_count[note["location"]] += 1
                if note["location"] not in total_location_notes:
                    total_location_notes[note["location"]] = 0
                total_location_notes[note["location"]] += 1
                if (
                    note["flexologist_name"].lower()
                    not in flexologist_with_opportunity_count
                ):
                    flexologist_with_opportunity_count[
                        note["flexologist_name"].lower()
                    ] = 0
                flexologist_with_opportunity_count[
                    note["flexologist_name"].lower()
                ] += 1
                if note["flexologist_name"] not in total_flexologist_note:
                    total_flexologist_note[note["flexologist_name"]] = 0
                total_flexologist_note[note["flexologist_name"]] += 1
            else:
                if note["location"] not in total_location_notes:
                    total_location_notes[note["location"]] = 0
                total_location_notes[note["location"]] += 1
                if note["flexologist_name"] not in total_flexologist_note:
                    total_flexologist_note[note["flexologist_name"]] = 0
                total_flexologist_note[note["flexologist_name"]] += 1

        notes_with_particular_opportunity = []
        locations_with_particular_opportunity_count = {}
        flexologist_with_particular_opportunity_count = {}

        for note in notes_with_opportunities:
            lowered_opps = [
                item.lower()
                for item in json.loads(note["note_oppurtunities"])
                if isinstance(item, str)
            ]
            if opportunity.lower() in lowered_opps:
                notes_with_particular_opportunity.append(note)
                if note["location"] not in locations_with_particular_opportunity_count:
                    locations_with_particular_opportunity_count[note["location"]] = 0
                locations_with_particular_opportunity_count[note["location"]] += 1
                if (
                    note["flexologist_name"].lower()
                    not in flexologist_with_particular_opportunity_count
                ):
                    flexologist_with_particular_opportunity_count[
                        note["flexologist_name"].lower()
                    ] = 0
                flexologist_with_particular_opportunity_count[
                    note["flexologist_name"].lower()
                ] += 1

        locations_with_particular_opportunity_percentage = {}
        flexologist_with_particular_opportunity_percentage = {}

        for location in locations_with_opportunity_count:
            if location in locations_with_particular_opportunity_count:
                locations_with_particular_opportunity_percentage[location] = round(
                    (
                        locations_with_particular_opportunity_count[location]
                        / locations_with_opportunity_count[location]
                    )
                    * 100,
                    2,
                )
            else:
                locations_with_particular_opportunity_percentage[location] = 0

        for flexologist in flexologist_with_opportunity_count:
            if flexologist in flexologist_with_particular_opportunity_count:
                flexologist_with_particular_opportunity_percentage[flexologist] = round(
                    (
                        flexologist_with_particular_opportunity_count[flexologist]
                        / flexologist_with_opportunity_count[flexologist]
                    )
                    * 100,
                    2,
                )
            else:
                flexologist_with_particular_opportunity_percentage[flexologist] = 0

        locations_with_particular_opportunity_percentage = dict(
            sorted(
                locations_with_particular_opportunity_percentage.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )

        sorted_locations_with_particular_opportunity_percentage = sorted(
            locations_with_particular_opportunity_percentage.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        flexologist_with_particular_opportunity_percentage = dict(
            sorted(
                flexologist_with_particular_opportunity_percentage.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )

        sorted_flexologist_with_particular_opportunity_percentage = sorted(
            flexologist_with_particular_opportunity_percentage.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "location": [
                        {
                            "location": location,
                            "percentage": percentage,
                            "particular_count": locations_with_particular_opportunity_count.get(
                                location, 0
                            ),
                            "total_count": locations_with_opportunity_count.get(
                                location, 0
                            ),
                            "percentage_note_quality": round(
                                (
                                    (
                                        total_location_notes.get(location, 0)
                                        - locations_with_opportunity_count.get(
                                            location, 0
                                        )
                                    )
                                    / total_location_notes.get(location, 0)
                                )
                                * 100,
                                2,
                            ),
                        }
                        for location, percentage in sorted_locations_with_particular_opportunity_percentage
                    ],
                    "flexologist": [
                        {
                            "flexologist": flexologist,
                            "percentage": percentage,
                            "particular_count": flexologist_with_particular_opportunity_count.get(
                                flexologist, 0
                            ),
                            "total_count": flexologist_with_opportunity_count.get(
                                flexologist, 0
                            ),
                            "percentage_note_quality": round(
                                (
                                    (
                                        total_flexologist_note.get(flexologist, 0)
                                        - flexologist_with_opportunity_count.get(
                                            flexologist, 0
                                        )
                                    )
                                    / total_flexologist_note.get(flexologist, 0)
                                )
                                * 100,
                                2,
                            ),
                        }
                        for flexologist, percentage in sorted_flexologist_with_particular_opportunity_percentage
                    ],
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
        user_id = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .execute()
        ).data[0]["admin_id"]
        data = request.json
        # rank_by = data.get("rank_by", "location")
        metric = data.get("metric", "total_visits")
        filter_metric = data.get("filter_metric", "all")
        duration = data["duration"]
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

        config_id = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", user_id)
            .execute()
        ).data
        if not config_id:
            return jsonify({"error": "No RPA config found", "status": "error"}), 400
        config_id = config_id[0]["id"]

        if metric == "total_client_visits":
            first = metric == "total_client_visits" and filter_metric == "first"
            subsequent = (
                metric == "total_client_visits" and filter_metric == "subsequent"
            )
            get_all = metric == "total_client_visits" and filter_metric == "all"
            first_timer = "YES" if first else "NO"
            offset = 0
            limit = 1000
            rpa_notes = []
            if first or subsequent:
                while True:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("first_timer", first_timer)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                    rpa_notes.extend(data)
                    if len(data) < limit:
                        break
                    offset += limit
            elif get_all:
                while True:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                    rpa_notes.extend(data)
                    if len(data) < limit:
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
            # filter_by = "location" if rank_by == "location" else "flexologist_name"
            count = {}
            count_flex = {}
            for note in rpa_notes:
                if note["location"] not in count:
                    count[note["location"]] = 0
                count[note["location"]] += 1
                if note["flexologist_name"] not in count_flex:
                    count_flex[note["flexologist_name"]] = 0
                count_flex[note["flexologist_name"]] += 1

            count = dict(
                sorted(
                    count.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )

            count_flex = dict(
                sorted(
                    count_flex.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": [
                            {"name": item, "count": count, "total": len(rpa_notes)}
                            for item, count in count.items()
                        ],
                        "data_flex": [
                            {"name": item, "count": count, "total": len(rpa_notes)}
                            for item, count in count_flex.items()
                        ],
                        "metric": metric,
                    }
                ),
                200,
            )

        if metric == "percentage_app_submission":
            offset = 0
            limit = 1000
            all_notes = []
            app_submitted = []
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .neq("status", "No Show")
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                all_notes.extend(data)
                if len(data) < limit:
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

            flexologists = (
                supabase.table("users")
                .select("*")
                .eq("admin_id", user_id)
                .eq("role_id", 3)
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

            for flexologist in flexologists:
                offset = 0
                limit = 1000
                while True:
                    app_submitted_by_flexologist = (
                        supabase.table("clubready_bookings")
                        .select("*")
                        .eq("user_id", flexologist["id"])
                        .eq("submitted", True)
                        .gte("created_at", start_date)
                        .lt("created_at", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                        .data
                    )
                    app_submitted.extend(app_submitted_by_flexologist)
                    if len(app_submitted_by_flexologist) < limit:
                        break
                    offset += limit

            total_visits_per_location = {}
            total_visits_per_flex = {}
            for note in all_notes:
                loc = note["location"]
                flex = (
                    note["flexologist_name"].lower() if note["flexologist_name"] else ""
                )
                total_visits_per_location[loc] = (
                    total_visits_per_location.get(loc, 0) + 1
                )
                total_visits_per_flex[flex] = total_visits_per_flex.get(flex, 0) + 1
            submitted_per_location = {}
            submitted_per_flex = {}
            for sub in app_submitted:
                loc = sub["location"].lower()
                flex = (
                    sub["flexologist_name"].lower() if sub["flexologist_name"] else ""
                )
                submitted_per_location[loc] = submitted_per_location.get(loc, 0) + 1
                submitted_per_flex[flex] = submitted_per_flex.get(flex, 0) + 1
            location_percentages = {}
            for loc in total_visits_per_location:
                sub = submitted_per_location.get(loc, 0)
                total = total_visits_per_location[loc]
                pct = round((sub / total) * 100, 2) if total > 0 else 0
                location_percentages[loc] = {"pct": pct, "total": total}
            sorted_locations = sorted(
                location_percentages.items(),
                key=lambda item: item[1]["pct"],
                reverse=True,
            )

            flex_percentages = {}
            for flex in total_visits_per_flex:
                sub = submitted_per_flex.get(flex, 0)
                total = total_visits_per_flex[flex]
                pct = round((sub / total) * 100, 2) if total > 0 else 0
                flex_percentages[flex] = {"pct": pct, "total": total}
            sorted_flex = sorted(
                flex_percentages.items(), key=lambda item: item[1]["pct"], reverse=True
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

            # if rank_by == "location":
            #     data = [{"name": loc, "count": pct} for loc, pct in sorted_locations]
            # else:
            #     data = [{"name": flex, "count": pct} for flex, pct in sorted_flex]
            data = [
                {"name": loc, "count": data_dict["pct"], "total": data_dict["total"]}
                for loc, data_dict in sorted_locations
            ]
            data_flex = [
                {"name": flex, "count": data_dict["pct"], "total": data_dict["total"]}
                for flex, data_dict in sorted_flex
            ]

            # Add overall percentage to data or response
            return (
                jsonify(
                    {
                        "status": "success",
                        "data": data,
                        "data_flex": data_flex,
                        "metric": metric,
                        "overall_percentage": overall_percentage,
                    }
                ),
                200,
            )

        first = metric == "note_quality_percentage" and filter_metric == "first"
        subsequent = (
            metric == "note_quality_percentage" and filter_metric == "subsequent"
        )
        get_all = metric == "note_quality_percentage" and filter_metric == "all"

        if first or subsequent:
            first_timer = "YES" if first else "NO"
            offset = 0
            limit = 1000
            all_notes = []
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .eq("first_timer", first_timer)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                all_notes.extend(data)
                if len(data) < limit:
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

            # filter_by = "location" if rank_by == "location" else "flexologist_name"

            group_sums = {}
            group_counts = {}
            group_sums_flex = {}
            group_counts_flex = {}
            for booking in all_notes:
                score = (
                    int(booking["note_score"]) if booking["note_score"] != "N/A" else 0
                )
                percentage = round(
                    (score / (18.0 if booking["first_timer"] == "YES" else 4.0)) * 100,
                    2,
                )
                group_key = (
                    booking["location"]
                    # if filter_by == "flexologist_name"
                    # else booking[filter_by]
                )
                group_key_flex = booking["flexologist_name"].lower()
                group_sums[group_key] = group_sums.get(group_key, 0) + percentage
                group_counts[group_key] = group_counts.get(group_key, 0) + 1
                group_sums_flex[group_key_flex] = (
                    group_sums_flex.get(group_key_flex, 0) + percentage
                )
                group_counts_flex[group_key_flex] = (
                    group_counts_flex.get(group_key_flex, 0) + 1
                )

            averages = {}
            for key in group_sums:
                averages[key] = {
                    "avg": (
                        round(group_sums[key] / group_counts[key], 2)
                        if group_counts[key] > 0
                        else 0
                    ),
                    "total": group_counts[key],
                }

            averages_flex = {}
            for key in group_sums_flex:
                averages_flex[key] = {
                    "avg": (
                        round(group_sums_flex[key] / group_counts_flex[key], 2)
                        if group_counts_flex[key] > 0
                        else 0
                    ),
                    "total": group_counts_flex[key],
                }

            sorted_averages = sorted(
                averages.items(), key=lambda item: item[1]["avg"], reverse=True
            )
            sorted_averages_flex = sorted(
                averages_flex.items(), key=lambda item: item[1]["avg"], reverse=True
            )

            data = [
                {"name": name, "count": data_dict["avg"], "total": data_dict["total"]}
                for name, data_dict in sorted_averages
            ]
            data_flex = [
                {"name": name, "count": data_dict["avg"], "total": data_dict["total"]}
                for name, data_dict in sorted_averages_flex
            ]

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": data,
                        "data_flex": data_flex,
                        "metric": metric,
                    }
                ),
                200,
            )

        if get_all:
            offset = 0
            limit = 1000
            all_notes = []
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                all_notes.extend(data)
                if len(data) < limit:
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

            # filter_by = "location" if rank_by == "location" else "flexologist_name"

            group_sums = {}
            group_counts = {}
            group_sums_flex = {}
            group_counts_flex = {}
            for booking in all_notes:
                score = (
                    int(booking["note_score"]) if booking["note_score"] != "N/A" else 0
                )
                percentage = round(
                    (score / (18.0 if booking["first_timer"] == "YES" else 4.0)) * 100,
                    2,
                )
                group_key = (
                    booking["location"].lower()
                    # if filter_by == "flexologist_name"
                    # else booking[filter_by]
                )
                group_key_flex = booking["flexologist_name"].lower()
                group_sums[group_key] = group_sums.get(group_key, 0) + percentage
                group_counts[group_key] = group_counts.get(group_key, 0) + 1
                group_sums_flex[group_key_flex] = (
                    group_sums_flex.get(group_key_flex, 0) + percentage
                )
                group_counts_flex[group_key_flex] = (
                    group_counts_flex.get(group_key_flex, 0) + 1
                )

            averages = {}
            for key in group_sums:
                averages[key] = {
                    "avg": (
                        round(group_sums[key] / group_counts[key], 2)
                        if group_counts[key] > 0
                        else 0
                    ),
                    "total": group_counts[key],
                }

            averages_flex = {}
            for key in group_sums_flex:
                averages_flex[key] = {
                    "avg": (
                        round(group_sums_flex[key] / group_counts_flex[key], 2)
                        if group_counts_flex[key] > 0
                        else 0
                    ),
                    "total": group_counts_flex[key],
                }

            sorted_averages = sorted(
                averages.items(), key=lambda item: item[1]["avg"], reverse=True
            )
            sorted_averages_flex = sorted(
                averages_flex.items(), key=lambda item: item[1]["avg"], reverse=True
            )

            data = [
                {"name": name, "count": data_dict["avg"], "total": data_dict["total"]}
                for name, data_dict in sorted_averages
            ]
            data_flex = [
                {"name": name, "count": data_dict["avg"], "total": data_dict["total"]}
                for name, data_dict in sorted_averages_flex
            ]

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": data,
                        "data_flex": data_flex,
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
        user_id = (
            supabase.table("users")
            .select("admin_id")
            .eq("id", user_data["user_id"])
            .execute()
        ).data[0]["admin_id"]
        data = request.json
        # rank_by = data.get("rank_by", "location")
        location = data.get("location", None)
        if not location:
            return jsonify({"error": "Location is required", "status": "error"}), 400
        metric = data.get("metric", "total_visits")
        filter_metric = data.get("filter_metric", "all")
        duration = data["duration"]
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

        config_id = (
            supabase.table("robot_process_automation_config")
            .select("id")
            .eq("admin_id", user_id)
            .execute()
        ).data
        if not config_id:
            return jsonify({"error": "No RPA config found", "status": "error"}), 400
        config_id = config_id[0]["id"]

        if metric == "total_client_visits":
            first = metric == "total_client_visits" and filter_metric == "first"
            subsequent = (
                metric == "total_client_visits" and filter_metric == "subsequent"
            )
            get_all = metric == "total_client_visits" and filter_metric == "all"
            first_timer = "YES" if first else "NO"
            offset = 0
            limit = 1000
            rpa_notes = []
            if first or subsequent:
                while True:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("first_timer", first_timer)
                        .eq("location", location)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                    rpa_notes.extend(data)
                    if len(data) < limit:
                        break
                    offset += limit
            elif get_all:
                while True:
                    data = (
                        supabase.table("robot_process_automation_notes_records")
                        .select("*")
                        .eq("config_id", config_id)
                        .eq("location", location)
                        .neq("status", "No Show")
                        .gte("appointment_date", start_date)
                        .lt("appointment_date", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                    ).data
                    rpa_notes.extend(data)
                    if len(data) < limit:
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
            # filter_by = "location" if rank_by == "location" else "flexologist_name"
            count_flex = {}
            for note in rpa_notes:
                if note["flexologist_name"] not in count_flex:
                    count_flex[note["flexologist_name"]] = 0
                count_flex[note["flexologist_name"]] += 1

            count_flex = dict(
                sorted(
                    count_flex.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": [
                            {"name": item, "count": count, "total": len(rpa_notes)}
                            for item, count in count_flex.items()
                        ],
                        "metric": metric,
                    }
                ),
                200,
            )

        if metric == "percentage_app_submission":
            offset = 0
            limit = 1000
            all_notes = []
            app_submitted = []
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .eq("location", location)
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .neq("status", "No Show")
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                all_notes.extend(data)
                if len(data) < limit:
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

            flexologists = (
                supabase.table("users")
                .select("*")
                .eq("admin_id", user_id)
                .eq("role_id", 3)
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

            for flexologist in flexologists:
                offset = 0
                limit = 1000
                while True:
                    app_submitted_by_flexologist = (
                        supabase.table("clubready_bookings")
                        .select("*")
                        .eq("user_id", flexologist["id"])
                        .eq("location", location)
                        .eq("submitted", True)
                        .gte("created_at", start_date)
                        .lt("created_at", end_date)
                        .range(offset, offset + limit - 1)
                        .execute()
                        .data
                    )
                    app_submitted.extend(app_submitted_by_flexologist)
                    if len(app_submitted_by_flexologist) < limit:
                        break
                    offset += limit

            total_visits_per_flex = {}
            for note in all_notes:
                flex = (
                    note["flexologist_name"].lower() if note["flexologist_name"] else ""
                )

                total_visits_per_flex[flex] = total_visits_per_flex.get(flex, 0) + 1

            submitted_per_flex = {}
            for sub in app_submitted:
                flex = (
                    sub["flexologist_name"].lower() if sub["flexologist_name"] else ""
                )
                submitted_per_flex[flex] = submitted_per_flex.get(flex, 0) + 1

            flex_percentages = {}
            for flex in total_visits_per_flex:
                sub = submitted_per_flex.get(flex, 0)
                total = total_visits_per_flex[flex]
                pct = round((sub / total) * 100, 2) if total > 0 else 0
                flex_percentages[flex] = {"pct": pct, "total": total}
            sorted_flex = sorted(
                flex_percentages.items(), key=lambda item: item[1]["pct"], reverse=True
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

            # if rank_by == "location":
            #     data = [{"name": loc, "count": pct} for loc, pct in sorted_locations]
            # else:
            #     data = [{"name": flex, "count": pct} for flex, pct in sorted_flex]
            data = [
                {"name": flex, "count": data_dict["pct"], "total": data_dict["total"]}
                for flex, data_dict in sorted_flex
            ]

            # Add overall percentage to data or response
            return (
                jsonify(
                    {
                        "status": "success",
                        "data": data,
                        "metric": metric,
                        "overall_percentage": overall_percentage,
                    }
                ),
                200,
            )

        first = metric == "note_quality_percentage" and filter_metric == "first"
        subsequent = (
            metric == "note_quality_percentage" and filter_metric == "subsequent"
        )
        get_all = metric == "note_quality_percentage" and filter_metric == "all"

        if first or subsequent:
            first_timer = "YES" if first else "NO"
            offset = 0
            limit = 1000
            all_notes = []
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .eq("first_timer", first_timer)
                    .eq("location", location)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                all_notes.extend(data)
                if len(data) < limit:
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

            # filter_by = "location" if rank_by == "location" else "flexologist_name"

            group_sums_flex = {}
            group_counts_flex = {}
            for booking in all_notes:
                score = (
                    int(booking["note_score"]) if booking["note_score"] != "N/A" else 0
                )
                percentage = round(
                    (score / (18.0 if booking["first_timer"] == "YES" else 4.0)) * 100,
                    2,
                )

                group_key_flex = booking["flexologist_name"].lower()
                group_sums_flex[group_key_flex] = (
                    group_sums_flex.get(group_key_flex, 0) + percentage
                )
                group_counts_flex[group_key_flex] = (
                    group_counts_flex.get(group_key_flex, 0) + 1
                )

            averages_flex = {}
            for key in group_sums_flex:
                averages_flex[key] = {
                    "avg": (
                        round(group_sums_flex[key] / group_counts_flex[key], 2)
                        if group_counts_flex[key] > 0
                        else 0
                    ),
                    "total": group_counts_flex[key],
                }

            sorted_averages_flex = sorted(
                averages_flex.items(), key=lambda item: item[1]["avg"], reverse=True
            )

            data = [
                {"name": name, "count": data_dict["avg"], "total": data_dict["total"]}
                for name, data_dict in sorted_averages_flex
            ]

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": data,
                        "metric": metric,
                    }
                ),
                200,
            )

        if get_all:
            offset = 0
            limit = 1000
            all_notes = []
            while True:
                data = (
                    supabase.table("robot_process_automation_notes_records")
                    .select("*")
                    .eq("config_id", config_id)
                    .eq("location", location)
                    .neq("status", "No Show")
                    .gte("appointment_date", start_date)
                    .lt("appointment_date", end_date)
                    .range(offset, offset + limit - 1)
                    .execute()
                ).data
                all_notes.extend(data)
                if len(data) < limit:
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

            # filter_by = "location" if rank_by == "location" else "flexologist_name"

            group_sums_flex = {}
            group_counts_flex = {}
            for booking in all_notes:
                score = (
                    int(booking["note_score"]) if booking["note_score"] != "N/A" else 0
                )
                percentage = round(
                    (score / (18.0 if booking["first_timer"] == "YES" else 4.0)) * 100,
                    2,
                )

                group_key_flex = booking["flexologist_name"].lower()
                group_sums_flex[group_key_flex] = (
                    group_sums_flex.get(group_key_flex, 0) + percentage
                )
                group_counts_flex[group_key_flex] = (
                    group_counts_flex.get(group_key_flex, 0) + 1
                )

            averages_flex = {}
            for key in group_sums_flex:
                averages_flex[key] = {
                    "avg": (
                        round(group_sums_flex[key] / group_counts_flex[key], 2)
                        if group_counts_flex[key] > 0
                        else 0
                    ),
                    "total": group_counts_flex[key],
                }

            sorted_averages_flex = sorted(
                averages_flex.items(), key=lambda item: item[1]["avg"], reverse=True
            )

            data = [
                {"name": name, "count": data_dict["avg"], "total": data_dict["total"]}
                for name, data_dict in sorted_averages_flex
            ]

            return (
                jsonify(
                    {
                        "status": "success",
                        "data": data,
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
