from flask import request, jsonify, Blueprint
from ..utils.utils import (
    get_user_bookings_from_clubready,
    decode_jwt_token,
    submit_notes,
)
from ..database.database import (
    save_notes,
    get_user_notes,
    get_notes_by_id,
    get_active_by_id,
)
from ..ai.aianalysis import scrutinize_notes, format_notes
import logging
from datetime import datetime, timezone
import json
from ..utils.middleware import require_bearer_token
import asyncio
import threading
import uuid
import pytz

routes = Blueprint("routes", __name__)


def get_client_timezone():
    """
    Extract timezone from request headers or use default UTC
    """
    timezone_header = request.headers.get("X-Client-Timezone")
    if timezone_header:
        try:
            pytz.timezone(timezone_header)
            return timezone_header
        except pytz.exceptions.UnknownTimeZoneError:
            logging.warning(f"Invalid timezone in header: {timezone_header}")

    if request.is_json:
        data = request.get_json()
        if data and "timezone" in data:
            try:
                pytz.timezone(data["timezone"])
                return data["timezone"]
            except pytz.exceptions.UnknownTimeZoneError:
                logging.warning(f"Invalid timezone in body: {data['timezone']}")

    return "UTC"


def get_client_datetime():
    """
    Get current datetime in client's timezone or UTC as fallback
    """
    client_tz = get_client_timezone()
    tz = pytz.timezone(client_tz)
    return datetime.now(tz)


def background_submit_notes(
    task_id,
    clubready_username,
    clubready_password,
    period,
    notes,
    location,
    client_name,
    coaching,
    client_date,
    client_tz,
):
    def local_get_client_datetime():
        tz = pytz.timezone(client_tz)
        return datetime.now(tz)

    try:
        supabase.table("clubready_bookings").update(
            {
                "task_status": "submitting",
                "task_message": "Notes submission running",
                "task_id": task_id,
                "submitted_notes": notes,
                "coaching_notes": coaching,
            }
        ).eq("client_name", client_name).eq("period", period).eq(
            "created_at", client_date
        ).execute()
        result = submit_notes(
            clubready_username, clubready_password, period, notes, location, client_name
        )

        if result["status"]:
            supabase.table("clubready_bookings").update(
                {
                    "submitted": True,
                    "submitted_at": local_get_client_datetime().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "task_status": "success",
                    "task_message": result["message"],
                    "task_id": task_id,
                    "task_error": None,
                }
            ).eq("client_name", client_name).eq("period", period).eq(
                "created_at", client_date
            ).execute()
            if result["same_client_period"]:
                supabase.table("clubready_bookings").update(
                    {
                        "submitted": True,
                        "submitted_at": local_get_client_datetime().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "submitted_notes": notes,
                        "coaching_notes": coaching,
                        "task_status": "success",
                        "task_message": result["message"],
                        "task_id": task_id,
                        "task_error": None,
                    }
                ).eq("client_name", client_name).eq(
                    "period", result["same_client_period"]
                ).eq(
                    "created_at", client_date
                ).execute()
        else:
            supabase.table("clubready_bookings").update(
                {
                    "task_status": "error",
                    "task_message": "Notes submission failed",
                    "task_id": task_id,
                    "submitted": False,
                    "submitted_notes": notes,
                    "coaching_notes": coaching,
                    "task_error": "No matching booking found",
                }
            ).eq("client_name", client_name).eq("period", period).eq(
                "created_at", client_date
            ).execute()
    except Exception as e:
        logging.error(f"Background task {task_id} failed: {str(e)}")
        supabase.table("clubready_bookings").update(
            {
                "task_status": "error",
                "task_message": "Submission failed",
                "task_id": task_id,
                "task_error": str(e),
            }
        ).eq("client_name", client_name).eq("created_at", client_date).execute()


@routes.route("/get_bookings", methods=["GET"])
@require_bearer_token
def get_bookings(token):
    try:
        reset = request.args.get("reset")
        user_data = decode_jwt_token(token)

        client_datetime = get_client_datetime()
        client_date = client_datetime.strftime("%Y-%m-%d")

        check_today_booking = (
            supabase.table("clubready_bookings")
            .select("*")
            .eq("user_id", user_data["user_id"])
            .eq("created_at", client_date)
            .execute()
        )
        if len(check_today_booking.data) > 0 and reset != "true":
            bookings = check_today_booking.data
        else:
            user = (
                supabase.table("users")
                .select("*")
                .eq("id", user_data["user_id"])
                .execute()
            )
            user_details = {
                "Username": user.data[0]["clubready_username"],
                "Password": user.data[0]["clubready_password"],
            }
            bookings = asyncio.run(get_user_bookings_from_clubready(user_details))
            if bookings["status"]:
                check_today_booking = (
                    supabase.table("clubready_bookings")
                    .select("*")
                    .eq("user_id", user_data["user_id"])
                    .eq("created_at", client_date)
                    .execute()
                )
                if len(check_today_booking.data) > 0:
                    for booking in check_today_booking.data:
                        if booking["submitted_notes"] is None:
                            supabase.table("clubready_bookings").delete().eq(
                                "id", booking["id"]
                            ).execute()

                existing_submitted_bookings = set()
                for today_booking in check_today_booking.data:
                    if today_booking["submitted_notes"] is not None:
                        existing_submitted_bookings.add(today_booking["booking_id"])

                def parse_time(t):
                    return datetime.strptime(t, "%I:%M %p").time()

                bookings["bookings"].sort(key=lambda b: parse_time(b["booking_time"]))

                for booking in bookings["bookings"]:
                    if booking["booking_id"] not in existing_submitted_bookings:
                        supabase.table("clubready_bookings").insert(
                            {
                                "user_id": user_data["user_id"],
                                "client_name": booking["client_name"].lower(),
                                "booking_id": booking["booking_id"],
                                "workout_type": booking["workout_type"],
                                "first_timer": booking["first_timer"],
                                "active_member": booking["active"],
                                "location": booking["location"].lower(),
                                "phone_number": booking["phone"],
                                "booking_time": booking["booking_time"],
                                "period": booking["event_date"],
                                "past_booking": booking["past"],
                                "flexologist_name": booking["flexologist_name"].lower(),
                                "submitted": False,
                                "submitted_notes": None,
                                "created_at": client_date,
                            }
                        ).execute()

                check_bookings = (
                    supabase.table("clubready_bookings")
                    .select("*")
                    .eq("user_id", user_data["user_id"])
                    .eq("created_at", client_date)
                    .order("id")
                    .execute()
                )
                bookings = check_bookings.data
            else:
                return (
                    jsonify(
                        {
                            "message": "incorrect username or password",
                            "status": "warning",
                        }
                    ),
                    400,
                )

        response = {
            "message": f"Bookings fetched successfully",
            "status": "success",
            "bookings": bookings,
        }
        return jsonify(response), 200

    except Exception as e:
        logging.error(f"Error in GET /api/resource: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


@routes.route("/add_notes", methods=["POST"])
@require_bearer_token
def add_notes(token):
    try:
        data = request.get_json()
        user_data = decode_jwt_token(token)
        note_data = {
            "flexologist_uid": user_data["user_id"],
            "note": data["note"],
            "time": get_client_datetime().strftime("%Y-%m-%d %H:%M:%S"),
            "voice": str(data["voice"]),
            "type": data["type"],
            "booking_id": data["bookingId"],
            "created_at": get_client_datetime().strftime("%Y-%m-%d %H:%M:%S"),
        }
        create_note = supabase.table("booking_notes").insert(note_data).execute()
        if create_note.data:
            return (
                jsonify({"message": "Notes added successfully", "status": "success"}),
                201,
            )
        else:
            return (
                jsonify({"message": "Notes addition failed", "status": "error"}),
                400,
            )
    except ValueError as ve:
        logging.warning(f"Validation error in POST /api/resource: {str(ve)}")
        return jsonify({"error": str(ve), "status": "error"}), 400
    except Exception as e:
        logging.error(f"Error in POST /api/resource: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


@routes.route("/get_client_history", methods=["POST"])
@require_bearer_token
def get_client_history(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        client_name = data["client_name"]
        client_history = (
            supabase.table("clubready_bookings")
            .select("*")
            .eq("client_name", client_name)
            .execute()
        )
        return (
            jsonify({"client_history": client_history.data, "status": "success"}),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST /api/stretchnote/get_client_history: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


@routes.route("/get_flexologist_history", methods=["GET"])
@require_bearer_token
def get_flexologist_history(token):
    try:
        user_data = decode_jwt_token(token)
        flexologist_history = (
            supabase.table("clubready_bookings")
            .select("*")
            .eq("flexologist_uid", user_data["user_id"])
            .execute()
        )
        return (
            jsonify(
                {"flexologist_history": flexologist_history.data, "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(
            f"Error in GET /api/stretchnote/get_flexologist_history: {str(e)}"
        )
        return jsonify({"error": "Internal server error", "status": "error"}), 500


@routes.route("/get_notes/<booking_id>", methods=["GET"])
@require_bearer_token
def get_notes(token, booking_id):
    try:
        user_data = decode_jwt_token(token)
        notes = (
            supabase.table("booking_notes")
            .select("*")
            .eq("booking_id", booking_id)
            .eq("flexologist_uid", user_data["user_id"])
            .execute()
        )
        if notes.data:
            return jsonify({"notes": notes.data, "status": "success"}), 200
        else:
            return jsonify({"message": "No notes found", "status": "error"}), 404
    except Exception as e:
        logging.error(f"Error in GET /api/resource: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


@routes.route("/get_questions/<booking_id>", methods=["GET"])
@require_bearer_token
def get_questions(token, booking_id):
    try:
        user_data = decode_jwt_token(token)
        notes = (
            supabase.table("booking_notes")
            .select("*")
            .eq("booking_id", booking_id)
            .eq("type", "user")
            .execute()
        )
        get_booking = (
            supabase.table("clubready_bookings")
            .select("*")
            .eq("user_id", user_data["user_id"])
            .eq("booking_id", booking_id)
            .execute()
        )
        if not get_booking.data:
            return jsonify({"message": "Booking not found", "status": "error"}), 404

        active = get_booking.data[0]["active_member"]
        questions = scrutinize_notes(notes, active)
        formatted_notes = format_notes(notes)

        note_data = {
            "flexologist_uid": user_data["user_id"],
            "note": json.dumps(
                questions["questions"]
                if "no questions" not in questions["questions"]
                else []
            ),
            "time": get_client_datetime().strftime("%Y-%m-%d %H:%M:%S"),
            "voice": "assistant",
            "type": "assistant",
            "booking_id": booking_id,
            "formatted_notes": json.dumps(formatted_notes),
            "created_at": get_client_datetime().strftime("%Y-%m-%d %H:%M:%S"),
        }
        create_note = supabase.table("booking_notes").insert(note_data).execute()
        if create_note.data:
            return (
                jsonify(
                    {
                        "questions": (
                            questions
                            if "no questions" not in questions["questions"]
                            else {"questions": []}
                        ),
                        "formatted_notes": formatted_notes,
                        "status": "success",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify({"message": "Notes addition failed", "status": "error"}),
                400,
            )
    except Exception as e:
        logging.error(f"Error in POST /api/resource: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


@routes.route("/submit_notes", methods=["POST"])
@require_bearer_token
def submit_notes_route(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        period = data["period"]
        notes = data["notes"]
        coaching = data["coaching"]
        client_name = data["client_name"]
        location = data["location"]
        client_tz = get_client_timezone()
        client_datetime = get_client_datetime()
        client_date = client_datetime.strftime("%Y-%m-%d")

        user_details = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not user_details.data:
            return jsonify({"error": "User not found", "status": "error"}), 404

        task_id = str(uuid.uuid4())

        thread = threading.Thread(
            target=background_submit_notes,
            args=(
                task_id,
                user_details.data[0]["clubready_username"],
                user_details.data[0]["clubready_password"],
                period,
                notes,
                location,
                client_name,
                coaching,
                client_date,
                client_tz,
            ),
        )
        thread.start()

        return (
            jsonify(
                {
                    "message": "Notes submitted successfully",
                    "status": "success",
                    "task_id": task_id,
                }
            ),
            202,
        )

    except Exception as e:
        logging.error(f"Error in POST /submit_notes: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


def init_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/process")
