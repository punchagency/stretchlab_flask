from flask import Blueprint, jsonify, request
from ..utils.middleware import require_bearer_token
from ..utils.utils import hash_password, decode_jwt_token
from datetime import datetime
import logging
import jwt
import os
import urllib.parse
from ..utils.mail import send_email
from ..notification import insert_notification


routes = Blueprint("user_management", __name__)


@routes.route("/get-managers", methods=["GET"])
@require_bearer_token
def get_managers_users(token):
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
        managers = (
            supabase.table("users")
            .select("id, full_name, status, email, invited_at,created_at")
            .in_("role_id", [4, 8])
            .eq("admin_id", user_data["user_id"])
            .execute()
            .data
        )
        return (
            jsonify({"message": "Managers fetched successfully", "data": managers}),
            200,
        )
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/invite-manager", methods=["POST"])
@require_bearer_token
def invite_manager(token):
    try:
        user_data = decode_jwt_token(token)
        check_user_exists_and_is_admin = (
            supabase.table("users")
            .select("*, roles(name)")
            .eq("id", user_data["user_id"])
            .in_("role_id", [1, 2])
            .execute()
        )
        if not check_user_exists_and_is_admin.data:
            return (
                jsonify({"message": "User is not an admin", "status": "error"}),
                401,
            )

        data = request.get_json()
        email = data.get("email")

        if not email:
            return jsonify({"message": "Email is required", "status": "error"}), 400

        check_user_non_manager = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .in_("role_id", [1, 2])
            .execute()
        )
        if check_user_non_manager.data:
            return (
                jsonify(
                    {
                        "message": "User already an admin cannot be made a manager",
                        "status": "warning",
                    }
                ),
                409,
            )
        check_user_flexologist = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .eq("role_id", 3)
            .execute()
        )
        if check_user_flexologist.data:
            return (
                jsonify(
                    {
                        "message": "User already a flexologist",
                        "status": "warning",
                    }
                ),
                403,
            )
        check_user_active = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .eq("role_id", 4)
            .eq("status", 1)
            .execute()
        )
        if check_user_active.data:
            return (
                jsonify({"message": "Manager already active", "status": "warning"}),
                409,
            )

        check_user_disabled = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .eq("status", 2)
            .eq("role_id", 4)
            .execute()
        )
        if check_user_disabled.data:
            return (
                jsonify(
                    {
                        "message": "Manager already disabled, grant access to continue",
                        "status": "warning",
                    }
                ),
                409,
            )
        check_user_invited = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .eq("status", 3)
            .eq("role_id", 4)
            .execute()
        )
        jwt_email = jwt.encode(
            {"email": email}, os.environ.get("JWT_SECRET_KEY"), algorithm="HS256"
        )
        if check_user_invited.data:
            send_email(
                "Invitation to Stretchnote Admin Panel",
                [email],
                None,
                f"<html><body><p>You have been invited to the <b>Stretchnote Admin Panel</b>.</p><p>Here is the link to the app: <a href='https://admin.stretchnote.com/invitation?email={jwt_email}'>Stretchnote Admin Panel</a></p></body></html>",
            )

            return (
                jsonify(
                    {
                        "message": "Manager previously invited. Resent email, check email for link",
                        "status": "success",
                    }
                ),
                200,
            )
        new_user = (
            supabase.table("users")
            .insert(
                {
                    "email": email.lower(),
                    "password": "empty",
                    "status": 3,
                    "role_id": 4,
                    "username": user_data["username"],
                    "admin_id": user_data["user_id"],
                    "is_verified": False,
                    "invited_at": datetime.now().isoformat(),
                }
            )
            .execute()
        )
        new_user = new_user.data[0]
        if new_user:
            status = send_email(
                "Invitation to Stretchnote Admin Panel",
                [email],
                None,
                f"<html><body><p>You have been invited to the <b>Stretchnote Admin Panel</b>.</p><p>Here is the link to the app: <a href='https://admin.stretchnote.com/invitation?email={jwt_email}'>Stretchnote Admin Panel</a></p></body></html>",
            )
            if status["success"]:
                return (
                    jsonify(
                        {"message": "Manager invited successfully", "status": "success"}
                    ),
                    200,
                )
            else:
                return (
                    jsonify(
                        {"message": "Invitation failed to send", "status": "error"}
                    ),
                    400,
                )
    except Exception as e:
        logging.error(f"Error in POST api/admin/process/invite-manager: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/update-status", methods=["POST"])
@require_bearer_token
def update_status(token):
    try:
        user_data = decode_jwt_token(token)
        check_user_exists_and_is_admin = (
            supabase.table("users")
            .select("*, roles(name)")
            .eq("id", user_data["user_id"])
            .in_("role_id", [1, 2])
            .execute()
        )
        if not check_user_exists_and_is_admin.data:
            return (
                jsonify({"message": "User is not an admin", "status": "error"}),
                401,
            )

        data = request.get_json()
        enable = data.get("enable", False)
        user_id = data.get("user_id")

        if not user_id:
            return (
                jsonify({"message": "User ID is required", "status": "error"}),
                400,
            )

        supabase.table("users").update({"status": 1 if enable else 2}).eq(
            "id", user_id
        ).execute()

        return (
            jsonify({"message": "Status updated successfully", "status": "success"}),
            200,
        )

    except Exception as e:
        logging.error(f"Error in POST api/admin/process/invite-manager: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/add-details", methods=["POST"])
def add_password():
    try:
        data = request.get_json()
        email = data.get("email")
        full_name = data.get("full_name")
        password = data.get("password")
        if not email or not password:
            return (
                jsonify(
                    {"message": "Email and password are required", "status": "error"}
                ),
                400,
            )

        user = supabase.table("users").select("*").eq("email", email).execute()

        if len(user.data) == 0:
            return (
                jsonify(
                    {
                        "message": "Manager does not exist",
                        "status": "error",
                    }
                ),
                404,
            )

        hashed_password = hash_password(password)
        updated_user = (
            supabase.table("users")
            .update(
                {
                    "password": hashed_password,
                    "status": 1,
                    "full_name": full_name,
                    "created_at": datetime.now().isoformat(),
                }
            )
            .eq("email", email)
            .execute()
        )

        insert_notification(
            updated_user.data[0]["id"],
            "Welcome to Stretchnote Admin!",
            "others",
        )

        return (
            jsonify({"message": "Password added successfully", "status": "success"}),
            200,
        )

    except Exception as e:
        logging.error(f"Error in POST /admin/user-management/add-password: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


def init_user_management_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/admin/user-management")
