from flask import Blueprint, request
from flask import jsonify
import logging
from ..utils.middleware import require_bearer_token
from ..utils.utils import decode_jwt_token
from datetime import datetime


routes = Blueprint("notification", __name__)


# Insert notification
def insert_notification(user_id, message, type):
    try:
        supabase.table("notifications").insert(
            {
                "user_id": user_id,
                "message": message,
                "type": type,
                "created_at": datetime.now().isoformat(),
                "is_read": False,
            }
        ).execute()
        return True
    except Exception as e:
        logging.error(f"Error in INSERT /notification: {str(e)}")
        return False


@routes.route("/", methods=["GET"])
@require_bearer_token
def get_notification(token):
    try:
        decoded_user = decode_jwt_token(token)
        user = (
            supabase.table("users")
            .select("*")
            .eq("id", decoded_user["user_id"])
            .execute()
            .data[0]
        )
        if not user:
            return jsonify({"message": "User not found"}), 404
        notifications = (
            supabase.table("notifications")
            .select("*")
            .eq("user_id", decoded_user["user_id"])
            .execute()
            .data
        )
        return jsonify(
            {
                "message": "Notifications fetched successfully",
                "status": "success",
                "notifications": notifications,
            },
            200,
        )
    except Exception as e:
        logging.error(f"Error in GET /notification: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/update", methods=["POST"])
@require_bearer_token
def update_notification(token):
    try:
        decoded_user = decode_jwt_token(token)
        user = (
            supabase.table("users")
            .select("*")
            .eq("id", decoded_user["user_id"])
            .execute()
            .data[0]
        )
        if not user:
            return jsonify({"message": "User not found"}), 404
        data = request.get_json()
        notification_id = data.get("notification_id")
        is_read = data.get("is_read")
        supabase.table("notifications").update({"is_read": is_read}).eq(
            "id", notification_id
        ).execute()
        return (
            jsonify(
                {"message": "Notification updated successfully", "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST /notification: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/mark-all-as-read", methods=["GET"])
@require_bearer_token
def mark_all_as_read(token):
    try:
        decoded_user = decode_jwt_token(token)
        user = (
            supabase.table("users")
            .select("*")
            .eq("id", decoded_user["user_id"])
            .execute()
            .data[0]
        )
        if not user:
            return jsonify({"message": "User not found"}), 404
        supabase.table("notifications").update({"is_read": True}).eq(
            "user_id", decoded_user["user_id"]
        ).execute()
        return (
            jsonify(
                {"message": "All notifications marked as read", "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST /notification/mark-all-as-read: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/delete/<notification_id>", methods=["DELETE"])
@require_bearer_token
def delete_notification(token, notification_id):
    try:
        decoded_user = decode_jwt_token(token)
        user = (
            supabase.table("users")
            .select("*")
            .eq("id", decoded_user["user_id"])
            .execute()
            .data[0]
        )
        if not user:
            return jsonify({"message": "User not found"}), 404
        supabase.table("notifications").delete().eq("id", notification_id).execute()
        return (
            jsonify(
                {"message": "Notification deleted successfully", "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in DELETE /notification: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


def init_notification(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/notification")
