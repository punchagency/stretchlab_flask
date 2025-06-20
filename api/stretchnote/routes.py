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
            bookings = json.loads(check_today_booking.data[0]["bookings"])
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
                if (
                    supabase.table("clubready_bookings")
                    .select("*")
                    .eq("user_id", user_data["user_id"])
                    .execute()
                    .data
                ):
                    supabase.table("clubready_bookings").update(
                        {
                            "bookings": json.dumps(bookings["bookings"]),
                            "created_at": datetime.now().strftime("%Y-%m-%d"),
                        }
                    ).eq("user_id", user_data["user_id"]).execute()
                else:
                    supabase.table("clubready_bookings").insert(
                        {
                            "user_id": user_data["user_id"],
                            "bookings": json.dumps(bookings["bookings"]),
                            "created_at": datetime.now().strftime("%Y-%m-%d"),
                        }
                    ).execute()

                bookings = bookings["bookings"]
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
        logging.error(f"Error in GET /api/stretchnote/get_bookings: {str(e)}")
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
        logging.error(f"Error in POST /api/stretchnote/add_notes: {str(e)}")
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
            .execute()
        )

        if get_booking.data:
            for booking in json.loads(get_booking.data[0]["bookings"]):
                if booking["booking_id"] == booking_id:
                    active = booking["active"]
                    break
        else:
            return jsonify({"message": "Booking not found", "status": "error"}), 404
        questions = scrutinize_notes(notes, active)
        formatted_notes = format_notes(notes)

        note_data = {
            "flexologist_uid": user_data["user_id"],
            "note": json.dumps(questions["questions"]),
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
                        "questions": questions,
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
        logging.error(f"Error in POST /api/stretchnote/get_questions: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


@routes.route("/submit_notes", methods=["POST"])
@require_bearer_token
def submit_notes_route(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        period = data["period"]
        notes = data["notes"]
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
        )
        if result["status"]:
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
        logging.error(f"Error in POST /api/stretchnote/submit_notes: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


def init_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/process")
