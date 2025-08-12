from flask import request, jsonify, Blueprint
from ..utils.utils import (
    validate_request,
    hash_password,
    verify_password,
    generate_verification_code,
    decode_jwt_token,
)
from ..utils.mail import send_email
from ..utils.two_factor import (
    verify_totp_code,
    verify_backup_code,
    remove_used_backup_code,
)
from ..database.database import remove_booking_created_at
from ..utils.middleware import require_bearer_token
import logging
import jwt
import os
from datetime import datetime, timedelta
from ..payment.stripe_utils import create_customer
from ..notification import insert_notification
import json


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
            return (
                jsonify(
                    {
                        "message": "Unauthorized access, you are not an admin",
                        "status": "error",
                    }
                ),
                400,
            )

        if user.data[0]["status"] == 2:
            return (
                jsonify(
                    {
                        "message": "Your account is disabled, please contact support",
                        "status": "error",
                    }
                ),
                400,
            )

        if user.data[0]["password"] == "empty" and user.data[0]["role_id"] == 4:
            jwt_email = jwt.encode(
                {"email": data["email"].lower()},
                os.environ.get("JWT_SECRET_KEY"),
                algorithm="HS256",
            )

            return (
                jsonify(
                    {
                        "message": "Please set your password",
                        "status": "error",
                        "requires_password": True,
                        "url": f"https://admin.stretchnote.com/invitation?email={jwt_email}",
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
            get_business_details = (
                supabase.table("businesses")
                .select("*")
                .eq("admin_id", user.data[0]["admin_id"])
                .execute()
            )
            if verify_password(data["password"], user.data[0]["password"]):
                if user.data[0]["two_factor_auth"]:
                    verification_code = generate_verification_code()
                    expiration_time = (
                        datetime.now() + timedelta(minutes=5)
                    ).isoformat()
                    supabase.table("users").update(
                        {
                            "verification_code": verification_code,
                            "verification_code_expires_at": expiration_time,
                        }
                    ).eq("id", user.data[0]["id"]).execute()
                    status = send_email(
                        "2FA Verification Code",
                        [user.data[0]["email"]],
                        None,
                        f"<html><body><p>Your 2FA verification code is {verification_code}. It will expire in 5 minutes.</p></body></html>",
                    )
                    return (
                        jsonify(
                            {
                                "message": "2FA verification code sent successfully",
                                "status": "success",
                                "requires_2fa": True,
                            }
                        ),
                        200,
                    )

                if user.data[0]["is_verified"] != True:
                    verification_code = generate_verification_code()
                    expiration_time = (
                        datetime.now() + timedelta(minutes=5)
                    ).isoformat()
                    supabase.table("users").update(
                        {
                            "verification_code": verification_code,
                            "verification_code_expires_at": expiration_time,
                        }
                    ).eq("id", user.data[0]["id"]).execute()
                    status = send_email(
                        "Verification Code",
                        [user.data[0]["email"]],
                        None,
                        f"<html><body><p>Your verification code is {verification_code}. It will expire in 5 minutes.</p></body></html>",
                    )

                token = jwt.encode(
                    {
                        "user_id": user.data[0].get("id"),
                        "email": user.data[0]["email"],
                        "role_id": user.data[0]["role_id"],
                        "role_name": role_name,
                        "rpa_verified": get_business_details.data[0][
                            "robot_process_automation_active"
                        ],
                        "note_verified": get_business_details.data[0][
                            "note_taking_active"
                        ],
                        "username": user.data[0]["username"],
                    },
                    SECRET_KEY,
                    algorithm="HS256",
                )
                return (
                    jsonify(
                        {
                            "message": (
                                "Logged in successfully"
                                if user.data[0]["is_verified"]
                                else "Please verify your email to proceed, check your email for the verification code"
                            ),
                            "status": "success",
                            "requires_2fa": False,
                            "user": {
                                "id": user.data[0]["id"],
                                "email": user.data[0]["email"],
                                "username": user.data[0]["username"],
                                "role_id": user.data[0]["role_id"],
                                "is_verified": user.data[0]["is_verified"],
                                "is_clubready_verified": user.data[0]["status"] != 5,
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

        else:
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
        logging.warning(f"Validation error in POST /auth/login: {str(ve)}")
        return jsonify({"message": str(ve), "status": "error"}), 400
    except Exception as e:
        logging.error(f"Error in POST /admin/auth/login: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/verify-2fa-login", methods=["POST"])
def verify_2fa_login():
    try:
        data = request.get_json()
        code = data.get("code")
        email = data.get("email")

        user = (
            supabase.table("users")
            .select("*, roles(name)")
            .eq("email", email.lower())
            .execute()
        )

        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        role_name = (
            user.data[0]["roles"]["name"]
            if user.data and user.data[0]["roles"]
            else "Unknown"
        )

        if (
            datetime.fromisoformat(user.data[0]["verification_code_expires_at"])
            > datetime.now()
        ):
            if user.data[0]["verification_code"] == code:
                get_business_details = (
                    supabase.table("businesses")
                    .select("*")
                    .eq("admin_id", user.data[0]["id"])
                    .execute()
                )
                supabase.table("users").update(
                    {
                        "verification_code": None,
                        "verification_code_expires_at": None,
                    }
                ).eq("id", user.data[0]["id"]).execute()
                token = jwt.encode(
                    {
                        "user_id": user.data[0].get("id"),
                        "email": user.data[0]["email"],
                        "role_id": user.data[0]["role_id"],
                        "role_name": role_name,
                        "username": user.data[0]["username"],
                        "rpa_verified": get_business_details.data[0][
                            "robot_process_automation_active"
                        ],
                        "note_verified": get_business_details.data[0][
                            "note_taking_active"
                        ],
                    },
                    SECRET_KEY,
                    algorithm="HS256",
                )
                return (
                    jsonify(
                        {
                            "message": "Logged in successfully",
                            "status": "success",
                            "token": token,
                            "user": {
                                "id": user.data[0]["id"],
                                "email": user.data[0]["email"],
                                "username": user.data[0]["username"],
                                "role_id": user.data[0]["role_id"],
                                "is_verified": user.data[0]["is_verified"],
                            },
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

    except Exception as e:
        logging.error(f"Error in POST /admin/auth/verify-2fa-login: {str(e)}")
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
        email = data.get("email")
        # frontend_url = os.environ.get("ADMIN_FRONTEND_URL")
        user = supabase.table("users").select("*").eq("email", email.lower()).execute()
        if len(user.data) == 0:
            return jsonify({"message": "User does not exist", "status": "error"}), 404

        if user.data[0]["role_id"] != 1 and user.data[0]["role_id"] != 2:
            return jsonify({"message": "User is not an admin", "status": "error"}), 400
        token = jwt.encode(
            {"email": email.lower()},
            SECRET_KEY,
            algorithm="HS256",
        )
        send_email(
            "Password Reset Link",
            [email],
            None,
            f"<html><body><p>Your password reset link is <a href='https://admin.stretchnote.com/reset-password/{token}'>here</a></p></body></html>",
        )
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
            .eq("email", user_data["email"].lower())
            .execute()
        )
        if len(user.data) == 0:
            return jsonify({"message": "User does not exist", "status": "error"}), 404
        hashed_password = hash_password(password)
        updated_user = (
            supabase.table("users")
            .update({"password": hashed_password})
            .eq("email", user_data["email"].lower())
            .execute()
        )
        if len(updated_user.data) == 0:
            return jsonify({"message": "Password reset failed", "status": "error"}), 400
        insert_notification(
            updated_user.data[0]["id"],
            f"Your password was reset",
            "others",
        )

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
                    "status": 5,
                    "created_at": datetime.now().isoformat(),
                }
            )
            .execute()
        )
        customer = create_customer(data["email"].lower(), data["username"])
        supabase.table("businesses").insert(
            {
                "username": data["username"],
                "admin_id": user.data[0]["id"],
                "customer_id": customer.id,
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
            None,
            f"<html><body><p>Your verification code is {verification_code}</p></body></html>",
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
                "rpa_verified": False,
                "note_verified": False,
            },
            SECRET_KEY,
            algorithm="HS256",
        )
        insert_notification(
            user.data[0]["id"],
            f"Welcome to Stretchnote Admin!",
            "others",
        )
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
                    "verification_code": verification_code,
                    "token": token,
                }
            ),
            201,
        )

    except Exception as e:
        logging.error(f"Error in POST /admin/auth/register: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/resend-2fa-verification-code", methods=["POST"])
def resend_2fa_verification_code():
    try:
        data = request.get_json()
        email = data.get("email")
        user = supabase.table("users").select("*").eq("email", email.lower()).execute()
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404
        verification_code = generate_verification_code()
        expiration_time = (datetime.now() + timedelta(minutes=5)).isoformat()
        supabase.table("users").update(
            {
                "verification_code": verification_code,
                "verification_code_expires_at": expiration_time,
            }
        ).eq("email", email.lower()).execute()
        send_email(
            "2FA Verification Code",
            [email],
            None,
            f"<html><body><p>Your 2FA verification code is {verification_code}. It will expire in 5 minutes.</p></body></html>",
        )
        return (
            jsonify(
                {
                    "message": "2FA verification code sent successfully",
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(
            f"Error in POST /admin/auth/resend-2fa-verification-code: {str(e)}"
        )
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
                    return (
                        jsonify(
                            {
                                "message": "Email verified successfully",
                                "is_clubready_verified": user.data[0]["status"] != 5,
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
        login = request.args.get("login")
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
                None,
                f"<html><body><p>Your verification code is {verification_code}. It will expire in 20 minutes.</p></body></html>",
            )
            return (
                jsonify(
                    {
                        "message": (
                            "2FA verification code sent successfully"
                            if login
                            else "Verification code sent successfully"
                        ),
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
