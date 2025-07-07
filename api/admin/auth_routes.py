from flask import request, jsonify, Blueprint
from ..utils.utils import (
    validate_request,
    hash_password,
    verify_password,
    generate_verification_code,
    decode_jwt_token,
)
from ..utils.mail import send_email
from ..database.database import remove_booking_created_at
from ..utils.middleware import require_bearer_token
import logging
import jwt
import os
from datetime import datetime, timedelta


routes = Blueprint("admin_auth", __name__)
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")


@routes.route("/login", methods=["POST", "OPTIONS"])
def login():

    if request.method == "OPTIONS":
        return "", 204
    try:
        schema = {
            "email": {
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

        user = (
            supabase.table("users")
            .select("*, roles(name)")
            .eq("email", data["email"].lower())
            .execute()
        )
        if len(user.data) == 0:
            logging.info(f"User {data['email']} does not exist")
            return (
                jsonify(
                    {
                        "message": "User does not exist, please register",
                        "status": "error",
                    }
                ),
                404,
            )
        if user.data[0]["role_id"] == 3:
            logging.info(f"User {data['email']} is not an admin")
            return (
                jsonify(
                    {
                        "message": "Unauthorized access, you are not an admin",
                        "status": "error",
                    }
                ),
                400,
            )
        role_name = (
            user.data[0]["roles"]["name"]
            if user.data and user.data[0]["roles"]
            else "Unknown"
        )
        if user.data:
            if verify_password(data["password"], user.data[0]["password"]):

                token = jwt.encode(
                    {
                        "user_id": user.data[0].get("id"),
                        "email": user.data[0]["email"],
                        "role_id": user.data[0]["role_id"],
                        "role_name": role_name,
                        "username": user.data[0]["username"],
                    },
                    SECRET_KEY,
                    algorithm="HS256",
                )
                logging.info(f"User {data['email']} logged in successfully - admin")
                return (
                    jsonify(
                        {
                            "message": (
                                "Logged in successfully"
                                if user.data[0]["is_verified"]
                                else "Please verify your email to proceed"
                            ),
                            "status": "success",
                            "user": {
                                "id": user.data[0]["id"],
                                "email": user.data[0]["email"],
                                "username": user.data[0]["username"],
                                "role_id": user.data[0]["role_id"],
                                "is_verified": user.data[0]["is_verified"],
                            },
                            "token": token,
                        }
                    ),
                    200,
                )
            else:
                logging.info(f"User {data['email']} failed to login - admin")
                return (
                    jsonify({"message": "Invalid credentials", "status": "error"}),
                    400,
                )

        else:
            logging.info(f"User {data['email']} does not exist - admin")
            return (
                jsonify(
                    {
                        "message": "User does not exist, please register",
                        "status": "error",
                    }
                ),
                404,
            )
    except ValueError as ve:
        logging.warning(f"Validation error in POST /admin/auth/login: {str(ve)}")
        return jsonify({"message": str(ve), "status": "error"}), 400
    except Exception as e:
        logging.error(f"Error in POST /admin/auth/login: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/check-username", methods=["GET"])
def check_username():
    try:

        username = request.args.get("username")

        user = (
            supabase.table("businesses").select("*").eq("username", username).execute()
        )
        if user.data:
            return (
                jsonify({"message": "Username already exists", "status": "error"}),
                400,
            )

        else:
            return (
                jsonify({"message": "Username is available", "status": "success"}),
                200,
            )
    except ValueError as ve:
        logging.warning(
            f"Validation error in POST /admin/auth/check-username: {str(ve)}"
        )
        return jsonify({"message": str(ve), "status": "error"}), 400
    except Exception as e:
        logging.error(f"Error in POST /admin/auth/check-username: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get("email").lower()
        frontend_url = os.environ.get("ADMIN_FRONTEND_URL")
        user = supabase.table("users").select("*").eq("email", email).execute()
        if len(user.data) == 0:
            return jsonify({"message": "User does not exist", "status": "error"}), 404

        if user.data[0]["role_id"] != 1 and user.data[0]["role_id"] != 2:
            return jsonify({"message": "User is not an admin", "status": "error"}), 400
        token = jwt.encode(
            {"email": email},
            SECRET_KEY,
            algorithm="HS256",
        )
        send_email(
            "Password Reset Link",
            [email],
            f"Your password reset link is {frontend_url}/reset-password/{token}",
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
        logging.error(f"Error in POST /admin/auth/reset-password: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        return "", 204
    try:
        schema = {
            "email": {
                "type": "string",
                "required": True,
                "minlength": 1,
                "maxlength": 120,
            },
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
            "role_id": {
                "type": "integer",
                "required": True,
            },
        }
        data = validate_request(request.get_json(), schema)
        user_exists = (
            supabase.table("users")
            .select("*")
            .eq("email", data["email"].lower())
            .execute()
        )
        if user_exists.data:
            return jsonify({"message": "User already exists", "status": "error"}), 400
        hashed_password = hash_password(data["password"])
        user = (
            supabase.table("users")
            .insert(
                {
                    "email": data["email"].lower(),
                    "username": data["username"],
                    "password": hashed_password,
                    "role_id": data["role_id"],
                    "status": 1,
                    "created_at": datetime.now().isoformat(),
                }
            )
            .execute()
        )
        supabase.table("businesses").insert(
            {
                "username": data["username"],
                "admin_id": user.data[0]["id"],
                "created_at": datetime.now().isoformat(),
            }
        ).execute()
        verification_code = generate_verification_code()
        expiration_time = (datetime.now() + timedelta(minutes=20)).isoformat()
        supabase.table("users").update(
            {
                "verification_code": verification_code,
                "verification_code_expires_at": expiration_time,
                "admin_id": user.data[0]["id"],
            }
        ).eq("id", user.data[0]["id"]).execute()
        status = send_email(
            "Verification Code",
            [user.data[0]["email"]],
            f"Your verification code is {verification_code}",
        )

        user = (
            supabase.table("users")
            .select("*, roles(name)")
            .eq("email", data["email"].lower())
            .execute()
        )
        role_name = (
            user.data[0]["roles"]["name"]
            if user.data and user.data[0]["roles"]
            else "Unknown"
        )
        token = jwt.encode(
            {
                "user_id": user.data[0].get("id"),
                "email": user.data[0]["email"],
                "role_id": user.data[0]["role_id"],
                "role_name": role_name,
                "username": user.data[0]["username"],
            },
            SECRET_KEY,
            algorithm="HS256",
        )
        logging.info(f"User {data['email']} registered successfully")
        return (
            jsonify(
                {
                    "message": "User registered successfully, please check your email for verification code",
                    "status": "success",
                    "user": {
                        "id": str(user.data[0]["id"]),
                        "email": user.data[0]["email"],
                        "username": user.data[0]["username"],
                        "role_id": user.data[0]["role_id"],
                    },
                    "token": token,
                }
            ),
            201,
        )

    except Exception as e:
        logging.error(f"Error in POST /admin/auth/register: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/verify", methods=["POST"])
@require_bearer_token
def verify(token):
    try:
        decoded_token = decode_jwt_token(token)
        if not decoded_token:
            return (
                jsonify(
                    {
                        "message": "Session expired, please login again",
                        "status": "error",
                    }
                ),
                401,
            )
        data = request.get_json()
        user = (
            supabase.table("users")
            .select("*")
            .eq("email", decoded_token["email"].lower())
            .execute()
        )
        if user.data:
            if (
                datetime.fromisoformat(user.data[0]["verification_code_expires_at"])
                > datetime.now()
            ):
                if user.data[0]["verification_code"] == data["code"]:
                    supabase.table("users").update(
                        {
                            "is_verified": True,
                            "verification_code": None,
                            "verification_code_expires_at": None,
                        }
                    ).eq("email", decoded_token["email"].lower()).execute()
                    logging.info(
                        f"Email {decoded_token['email']} verified successfully"
                    )
                    return (
                        jsonify(
                            {
                                "message": "Email verified successfully",
                                "status": "success",
                            }
                        ),
                        200,
                    )
                else:
                    return (
                        jsonify(
                            {"message": "Invalid verification code", "status": "error"}
                        ),
                        400,
                    )
            else:
                return (
                    jsonify(
                        {
                            "message": "Verification code expired, request a new one",
                            "status": "error",
                        }
                    ),
                    400,
                )
        else:
            return jsonify({"message": "User not found", "status": "error"}), 404
    except Exception as e:
        logging.error(f"Error in POST /admin/auth/verify: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/resend-verification-code", methods=["GET"])
@require_bearer_token
def resend_verification_code(token):
    try:
        decoded_token = decode_jwt_token(token)
        if not decoded_token:
            return (
                jsonify(
                    {
                        "message": "Session expired, please login again",
                        "status": "error",
                    }
                ),
                401,
            )
        user = (
            supabase.table("users")
            .select("*")
            .eq("email", decoded_token["email"].lower())
            .execute()
        )
        if user.data:
            verification_code = generate_verification_code()
            expiration_time = (datetime.now() + timedelta(minutes=20)).isoformat()
            supabase.table("users").update(
                {
                    "verification_code": verification_code,
                    "verification_code_expires_at": expiration_time,
                }
            ).eq("email", decoded_token["email"].lower()).execute()
            send_email(
                "Verification Code",
                [user.data[0]["email"]],
                f"Your verification code is {verification_code}",
            )
            logging.info(
                f"Verification code resent successfully to {user.data[0]['email']}"
            )
            return (
                jsonify(
                    {
                        "message": "Verification code sent successfully",
                        "status": "success",
                    }
                ),
                200,
            )
        else:
            return jsonify({"message": "User not found", "status": "error"}), 404
    except Exception as e:
        logging.error(f"Error in POST /admin/auth/resend-verification-code: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/logout", methods=["GET"])
@require_bearer_token
def logout(token):
    try:
        result = remove_booking_created_at(token)
        if result["status"]:
            return (
                jsonify({"message": result["message"], "status": "success"}),
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
        logging.error(f"Error in POST /admin/auth/logout: {str(e)}")
        return jsonify({"error": "Internal server error", "status": "error"}), 500


def init_admin_auth_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/admin/auth")
