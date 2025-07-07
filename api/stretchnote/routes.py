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
from datetime import datetime
import json
from ..utils.middleware import require_bearer_token
import asyncio

routes = Blueprint("routes", __name__)


@routes.route("/get_bookings", methods=["GET"])
@require_bearer_token
def get_bookings(token):
    try:
        reset = request.args.get("reset")
        user_data = decode_jwt_token(token)

        check_today_booking = (
            supabase.table("clubready_bookings")
            .select("*")
            .eq("user_id", user_data["user_id"])
            .eq("created_at", datetime.now().strftime("%Y-%m-%d"))
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
                    .eq("created_at", datetime.now().strftime("%Y-%m-%d"))
                    .execute()
                )
                if len(check_today_booking.data) > 0:
                    supabase.table("clubready_bookings").delete().eq(
                        "user_id", user_data["user_id"]
                    ).eq("created_at", datetime.now().strftime("%Y-%m-%d")).execute()
                for booking in bookings["bookings"]:
                    supabase.table("clubready_bookings").insert(
                        {
                            "user_id": user_data["user_id"],
                            "client_name": booking["client_name"],
                            "booking_id": booking["booking_id"],
                            "workout_type": booking["workout_type"],
                            "first_timer": booking["first_timer"],
                            "active_member": booking["active"],
                            "location": booking["location"],
                            "phone_number": booking["phone"],
                            "booking_time": booking["booking_time"],
                            "period": booking["event_date"],
                            "past_booking": booking["past"],
                            "flexologist_name": booking["flexologist_name"],
                            "submitted": False,
                            "submitted_notes": None,
                            "created_at": datetime.now().strftime("%Y-%m-%d"),
                        }
                    ).execute()

                check_bookings = (
                    supabase.table("clubready_bookings")
                    .select("*")
                    .eq("user_id", user_data["user_id"])
                    .eq("created_at", datetime.now().strftime("%Y-%m-%d"))
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
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "voice": str(data["voice"]),
            "type": data["type"],
            "booking_id": data["bookingId"],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
            logging.info(f"Notes fetched successfully for user {user_data['email']}")
            return jsonify({"notes": notes.data, "status": "success"}), 200
        else:
            return jsonify({"message": "No notes found", "status": "error"}), 404
    except Exception as e:
        logging.error(f"Error in GET /api/stretchnote/get_notes: {str(e)}")
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
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "voice": "assistant",
            "type": "assistant",
            "booking_id": booking_id,
            "formatted_notes": json.dumps(formatted_notes),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
        user_details = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )

        result = submit_notes(
            user_details.data[0]["clubready_username"],
            user_details.data[0]["clubready_password"],
            period,
            notes,
            location,
            client_name,
        )
        if result["status"]:
            supabase.table("clubready_bookings").update(
                {
                    "submitted": True,
                    "submitted_notes": notes,
                    "coaching_notes": coaching,
                    "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            ).eq("client_name", client_name).eq(
                "created_at", datetime.now().strftime("%Y-%m-%d")
            ).execute()
            return (
                jsonify({"message": result["message"], "status": "success"}),
                200,
            )
        else:
            return (
                jsonify({"message": "Notes submission failed", "status": "error"}),
                400,
            )
    except Exception as e:
        logging.error(f"Error in POST /api/resource: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


def init_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/process")
