from flask import request, jsonify, Blueprint
from ..utils.utils import (
    validate_request,
    clubready_login,
    verify_password,
    decode_jwt_token,
    hash_password,
)
from ..utils.mail import send_email
from ..database.database import remove_booking_created_at
from ..utils.middleware import require_bearer_token
import logging
import jwt
import os
from datetime import datetime

routes = Blueprint("stretchnote_auth", __name__)
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")


@routes.route("/clubready-login", methods=["POST"])
@require_bearer_token
def clubready_validate(token):

    try:
        user_data = decode_jwt_token(token)
        schema = {
            "username": {
                "type": "string",
                "required": True,
                "minlength": 1,
                "maxlength": 120,
            },
            "password": {
                "type": "string",
                "required": True,
                "minlength": 1,
                "maxlength": 120,
            },
        }
        data = validate_request(request.get_json(), schema)

        result = clubready_login(data)
        if result["status"]:
            updated_user = (
                supabase.table("users")
                .update(
                    {
                        "clubready_username": data["username"],
                        "clubready_password": result["hashed_password"],
                        "clubready_location_id": result["location_id"],
                        "clubready_user_id": result["user_id"],
                        "full_name": result["full_name"],
                        "status": 1,
                        "is_verified": True,
                    }
                )
                .eq("id", user_data["user_id"])
                .execute()
            )
            if len(updated_user.data) == 0:
                return (
                    jsonify(
                        {
                            "message": "There was an error, please try again",
                            "status": "error",
                        }
                    ),
                    400,
                )
            else:
                return (
                    jsonify(
                        {
                            "message": "Clubready credentials updated successfully",
                            "status": "success",
                        }
                    ),
                    200,
                )
        else:
            return (
                jsonify({"message": "Login failed", "status": "error"}),
                400,
            )

    except ValueError as ve:
        logging.warning(f"Validation error in POST stretchnote/auth/login: {str(ve)}")
        return jsonify({"message": str(ve), "status": "error"}), 400
    except Exception as e:
        logging.error(f"Error in POST /stretchnote/auth/login: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()

        user = (
            supabase.table("users")
            .select("*, roles(name)")
            .eq("email", data["email"].lower())
            .execute()
        )
        if len(user.data) == 0:
            return jsonify({"message": "User not found", "status": "error"}), 404
        if user.data[0]["status"] == 2:
            return (
                jsonify(
                    {"message": "User is disabled, contact admin", "status": "error"}
                ),
                400,
            )

        if user.data[0]["role_id"] != 3:
            return (
                jsonify(
                    {
                        "message": "User is not a flexologist, cannot proceed",
                        "status": "error",
                    }
                ),
                400,
            )
        # if user.data[0]["username"] != data["subdomain"]:
        #     return (
        #         jsonify(
        #             {
        #                 "message": "You are not authorized to login to this studio domain",
        #                 "status": "error",
        #             }
        #         ),
        #         400,
        #     )

        if verify_password(data["password"], user.data[0]["password"]):

            token = jwt.encode(
                {
                    "user_id": user.data[0].get("id"),
                    "email": user.data[0]["email"],
                    "role_id": user.data[0]["role_id"],
                    "role_name": "flexologist",
                    "username": user.data[0]["username"],
                    "status": user.data[0]["status"],
                },
                SECRET_KEY,
                algorithm="HS256",
            )

            if user.data[0]["status"] == 3:
                supabase.table("users").update({"status": 4}).eq(
                    "id", user.data[0]["id"]
                ).execute()
            logging.info(
                f"User {user.data[0]['email']} logged in successfully - flexologist"
            )
            return (
                jsonify(
                    {
                        "message": (
                            "Logged in successfully"
                            if user.data[0]["status"] == 1
                            else "Logged in successfully, activate your account"
                        ),
                        "status": "success",
                        "user": {
                            "id": user.data[0]["id"],
                            "email": user.data[0]["email"],
                            "username": user.data[0]["username"],
                            "role_id": user.data[0]["role_id"],
                            "is_verified": user.data[0]["is_verified"],
                            "status": user.data[0]["status"],
                        },
                        "token": token,
                    }
                ),
                200,
            )
        else:
            return (
                jsonify({"message": "Invalid credentials", "status": "error"}),
                400,
            )

    except Exception as e:
        logging.error(f"Error in POST /stretchnote/auth/login: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/change-password", methods=["POST"])
@require_bearer_token
def change_password(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()

        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if len(user.data) == 0:
            return (
                jsonify(
                    {
                        "message": "You don't have an account, or you are not logged in",
                        "status": "error",
                    }
                ),
                404,
            )

        if verify_password(data["old_password"], user.data[0]["password"]):
            hashed_password = hash_password(data["new_password"])
            supabase.table("users").update(
                {
                    "password": hashed_password,
                    "status": 5,
                    "created_at": datetime.now().isoformat(),
                }
            ).eq("id", user_data["user_id"]).execute()

            return (
                jsonify(
                    {"message": "Password changed successfully", "status": "success"}
                ),
                200,
            )
        else:
            return (
                jsonify({"message": "Invalid old password", "status": "error"}),
                400,
            )

    except Exception as e:
        logging.error(f"Error in POST /stretchnote/auth/change-password: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get("email").lower()
        # frontend_url = request.headers.get("Origin")
        user = supabase.table("users").select("*").eq("email", email).execute()
        if len(user.data) == 0:
            logging.info(f"User {email} does not exist")
            return jsonify({"message": "User does not exist", "status": "error"}), 404

        if user.data[0]["role_id"] != 3:
            logging.info(f"User {email} is not a flexologist")
            return (
                jsonify({"message": "User is not a flexologist", "status": "error"}),
                400,
            )
        if user.data[0]["status"] != 1:
            logging.info(f"User {email} is not active")
            return (
                jsonify(
                    {
                        "message": "User is not active, contact admin",
                        "status": "error",
                    }
                ),
                400,
            )
        token = jwt.encode(
            {"email": email},
            SECRET_KEY,
            algorithm="HS256",
        )
        send_email(
            "Password Reset Link",
            [email],
            f"Your password reset link is https://www.stretchnote.com/reset-password/{token}",
        )
        logging.info(f"Password reset link sent successfully to {email}")
        return (
            jsonify(
                {
                    "message": "Password reset link sent successfully",
                    "status": "success",
                }
            ),
            200,
        )

    except Exception as e:
        logging.error(f"Error in POST /admin/auth/change-password: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/reset-password", methods=["POST"])
def reset_password():
    try:
        data = request.get_json()
        token = data.get("token")
        password = data.get("password")
        user_data = decode_jwt_token(token)
        user = (
            supabase.table("users")
            .select("*")
            .eq("email", user_data["email"])
            .execute()
        )
        if len(user.data) == 0:
            return jsonify({"message": "User does not exist", "status": "error"}), 404

        hashed_password = hash_password(password)
        updated_user = (
            supabase.table("users")
            .update({"password": hashed_password})
            .eq("email", user_data["email"])
            .execute()
        )
        if len(updated_user.data) == 0:
            return jsonify({"message": "Password reset failed", "status": "error"}), 400
        logging.info(f"Password reset successfully for {user_data['email']}")
        return (
            jsonify({"message": "Password reset successfully", "status": "success"}),
            200,
        )

    except Exception as e:
        logging.error(f"Error in POST /stretchnote/auth/reset-password: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/logout", methods=["GET"])
@require_bearer_token
def logout(token):
    try:
        # result = remove_booking_created_at(token)
        user_data = decode_jwt_token(token)
        update_booking_created_at = (
            supabase.table("clubready_bookings")
            .update({"created_at": None})
            .eq("user_id", user_data["user_id"])
            .execute()
        )
        if update_booking_created_at.data:
            logging.info(f"User {user_data['email']} logged out successfully")
            return (
                jsonify({"message": "Logged out successfully", "status": "success"}),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "message": "An error occurred when logging out",
                        "status": "error",
                    }
                ),
                400,
            )
    except Exception as e:
        logging.error(f"Error in POST /stretchnote/auth/logout: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


def init_stretchnote_auth_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/stretchnote/auth")
