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
from ..payment.stripe_utils import create_subscription, update_subscription
from ..notification import insert_notification

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
        redo = request.args.get("redo", "false")

        result = clubready_login(data)
        get_super_admin = (
            supabase.table("users")
            .select("id,role_id")
            .eq("username", user_data["username"])
            .in_("role_id", [1, 2])
            .execute()
        )
        if result["status"]:
            check_subscription = (
                supabase.table("businesses")
                .select("*")
                .eq("username", user_data["username"])
                .execute()
            )

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
                if get_super_admin.data[0]["role_id"] != 1:
                    if not check_subscription.data[0]["note_taking_subscription_id"]:
                        get_price = (
                            supabase.table("prices")
                            .select("price_id")
                            .eq("type", "flexologist")
                            .execute()
                        )
                        subscription = create_subscription(
                            check_subscription.data[0]["customer_id"],
                            get_price.data[0]["price_id"],
                        )
                        supabase.table("businesses").update(
                            {
                                "note_taking_subscription_id": subscription[
                                    "subscription_id"
                                ],
                                "note_taking_subscription_status": subscription[
                                    "status"
                                ],
                                "note_taking_active": True,
                            }
                        ).eq("username", user_data["username"]).execute()

                    else:
                        if redo != "true":
                            update_subscription(
                                check_subscription.data[0][
                                    "note_taking_subscription_id"
                                ]
                            )

                user = (
                    supabase.table("users")
                    .select("*")
                    .eq("id", user_data["user_id"])
                    .execute()
                )
                insert_notification(
                    user.data[0]["admin_id"],
                    f"{user.data[0]['full_name']} has verified clubready credentials",
                    "note taking",
                )
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

        check_admin_subscription_active = (
            supabase.table("businesses")
            .select("note_taking_active, note_taking_subscription_id")
            .eq("admin_id", user.data[0]["admin_id"])
            .execute()
        )
        get_admin = (
            supabase.table("users")
            .select("role_id")
            .eq("id", user.data[0]["admin_id"])
            .execute()
        )
        if (
            not check_admin_subscription_active.data[0]["note_taking_active"]
            and check_admin_subscription_active.data[0]["note_taking_subscription_id"]
            and get_admin.data[0]["role_id"] != 1
        ):
            return (
                jsonify(
                    {
                        "message": "Admin subscription is not active, contact admin",
                        "status": "error",
                    }
                ),
                400,
            )
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

        if user.data[0]["password"] == "empty":
            return (
                jsonify(
                    {
                        "message": "User is yet to verify email, please check your email or contact admin",
                        "status": "error",
                    }
                ),
                400,
            )

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

                insert_notification(
                    user.data[0]["admin_id"],
                    f"User with email {user.data[0]['email']} has joined your team but yet to verify clubready credentials",
                    "note taking",
                )
            supabase.table("users").update(
                {"last_login": datetime.now().isoformat()}
            ).eq("id", user.data[0]["id"]).execute()
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
def change_password():
    try:
        data = request.get_json()
        email = data.get("email")
        new_password = data.get("new_password")

        if not email or not new_password:
            return (
                jsonify(
                    {
                        "message": "Email and new password are required",
                        "status": "error",
                    }
                ),
                400,
            )

        user = supabase.table("users").select("*").eq("email", email).execute()
        if len(user.data) == 0:
            return (
                jsonify(
                    {
                        "message": "User does not exist",
                        "status": "error",
                    }
                ),
                404,
            )

        if user.data[0]["password"] != "empty":
            return (
                jsonify(
                    {
                        "message": "Password already exists, please login",
                        "status": "error",
                    }
                ),
                400,
            )

        hashed_password = hash_password(new_password)
        supabase.table("users").update(
            {
                "password": hashed_password,
                "status": 5,
                "created_at": datetime.now().isoformat(),
            }
        ).eq("email", email).execute()

        return (
            jsonify({"message": "Password created successfully", "status": "success"}),
            200,
        )

    except Exception as e:
        logging.error(f"Error in POST /stretchnote/auth/change-password: {str(e)}")
        return jsonify({"message": "Internal server error", "status": "error"}), 500


@routes.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get("email")
        # frontend_url = request.headers.get("Origin")
        user = supabase.table("users").select("*").eq("email", email).execute()
        if len(user.data) == 0:
            return jsonify({"message": "User does not exist", "status": "error"}), 404

        if user.data[0]["role_id"] != 3:
            return (
                jsonify({"message": "User is not a flexologist", "status": "error"}),
                400,
            )
        if (
            user.data[0]["status"] not in [1, 4, 5]
            or user.data[0]["password"] == "empty"
        ):
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
        insert_notification(
            user.data[0]["id"],
            f"Your password was reset",
            "others",
        )
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
