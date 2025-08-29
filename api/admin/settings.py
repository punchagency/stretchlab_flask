from flask import Blueprint, request, jsonify
from ..utils.middleware import require_bearer_token
from ..utils.utils import decode_jwt_token
from ..utils.mail import send_email
from ..utils.utils import generate_verification_code
from datetime import datetime, timedelta
import logging
import json
import uuid
from werkzeug.utils import secure_filename
from ..utils.settings import save_image_to_s3, delete_image_from_s3
import io
from ..utils.utils import (
    verify_password,
    hash_password,
    reverse_hash_credentials,
    hash_credentials,
    clubready_admin_login,
)
from ..notification import insert_notification
from ..payment.stripe_utils import modify_customer_email

routes = Blueprint("settings", __name__)


@routes.route("/two-factor-auth/enable", methods=["GET"])
@require_bearer_token
def enable_two_factor_auth(token):
    try:
        user_data = decode_jwt_token(token)

        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )

        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        user_record = user.data[0]

        if user_record.get("two_factor_auth"):
            return (
                jsonify({"message": "2FA is already enabled", "status": "error"}),
                400,
            )

        verification_code = generate_verification_code()
        expiration_time = (datetime.now() + timedelta(minutes=5)).isoformat()
        supabase.table("users").update(
            {
                "verification_code": verification_code,
                "verification_code_expires_at": expiration_time,
            }
        ).eq("id", user.data[0]["id"]).execute()
        status = send_email(
            "2FA Verification Code",
            [user.data[0]["email"]],
            f"Your 2FA verification code is {verification_code}",
        )

        return (
            jsonify(
                {
                    "message": "2FA setup initiated",
                    "status": "success",
                }
            ),
            200,
        )

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/settings/two-factor-auth/enable: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/two-factor-auth/verify", methods=["POST"])
@require_bearer_token
def verify_two_factor_setup(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()

        if not data.get("code"):
            return (
                jsonify(
                    {"message": "Verification code is required", "status": "error"}
                ),
                400,
            )

        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )

        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        if (
            datetime.fromisoformat(user.data[0]["verification_code_expires_at"])
            > datetime.now()
        ):
            if user.data[0]["verification_code"] == data["code"]:
                supabase.table("users").update(
                    {
                        "two_factor_auth": True,
                        "verification_code": None,
                        "verification_code_expires_at": None,
                    }
                ).eq("id", user.data[0]["id"]).execute()
                insert_notification(
                    user_data["user_id"],
                    f"2FA enabled successfully",
                    "others",
                )
                return (
                    jsonify(
                        {
                            "message": "2FA enabled successfully",
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

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/settings/two-factor-auth/verify: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/two-factor-auth/disable", methods=["GET"])
@require_bearer_token
def disable_two_factor_auth(token):
    try:
        user_data = decode_jwt_token(token)

        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )

        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        user_record = user.data[0]

        if not user_record.get("two_factor_auth"):
            return jsonify({"message": "2FA is not enabled", "status": "error"}), 400

        verification_code = generate_verification_code()
        expiration_time = (datetime.now() + timedelta(minutes=5)).isoformat()
        supabase.table("users").update(
            {
                "verification_code": verification_code,
                "verification_code_expires_at": expiration_time,
            }
        ).eq("id", user.data[0]["id"]).execute()
        status = send_email(
            "2FA Verification Code",
            [user.data[0]["email"]],
            f"Your 2FA verification code is {verification_code}",
        )

        return (
            jsonify(
                {
                    "message": "2FA disable process initiated, please check your email for the verification code",
                    "status": "success",
                }
            ),
            200,
        )

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/settings/two-factor-auth/disable: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/two-factor-auth/disable/verify", methods=["POST"])
@require_bearer_token
def verify_two_factor_disable(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()

        if not data.get("code"):
            return (
                jsonify(
                    {"message": "Verification code is required", "status": "error"}
                ),
                400,
            )

        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )

        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        user_record = user.data[0]

        if not user_record.get("two_factor_auth"):
            return jsonify({"message": "2FA is not enabled", "status": "error"}), 400

        if (
            datetime.fromisoformat(user.data[0]["verification_code_expires_at"])
            > datetime.now()
        ):
            if user.data[0]["verification_code"] == data["code"]:
                supabase.table("users").update(
                    {
                        "two_factor_auth": False,
                        "verification_code": None,
                        "verification_code_expires_at": None,
                    }
                ).eq("id", user.data[0]["id"]).execute()

                insert_notification(
                    user_data["user_id"],
                    f"2FA disabled successfully",
                    "others",
                )

                return (
                    jsonify(
                        {
                            "message": "2FA disabled successfully",
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

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/settings/two-factor-auth/disable: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/two-factor-auth/resend-code", methods=["GET"])
@require_bearer_token
def resend_verification_code(token):
    try:
        user_data = decode_jwt_token(token)

        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )

        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        user_record = user.data[0]

        if not user_record.get("verification_code"):
            return (
                jsonify(
                    {
                        "message": "No verification code request found. Please initiate 2FA enable/disable first",
                        "status": "error",
                    }
                ),
                400,
            )

        if (
            user_record.get("verification_code_expires_at")
            and datetime.fromisoformat(user_record["verification_code_expires_at"])
            > datetime.now()
        ):
            return (
                jsonify(
                    {
                        "message": "Previous verification code is still valid. Please use the existing code or wait for it to expire",
                        "status": "error",
                    }
                ),
                400,
            )

        verification_code = generate_verification_code()
        expiration_time = (datetime.now() + timedelta(minutes=5)).isoformat()

        supabase.table("users").update(
            {
                "verification_code": verification_code,
                "verification_code_expires_at": expiration_time,
            }
        ).eq("id", user_record["id"]).execute()

        status = send_email(
            "2FA Verification Code",
            [user_record["email"]],
            f"Your new 2FA verification code is {verification_code}",
        )

        return (
            jsonify(
                {
                    "message": "New verification code sent successfully",
                    "status": "success",
                }
            ),
            200,
        )

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/settings/two-factor-auth/resend-code: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/two-factor-auth/status", methods=["GET"])
@require_bearer_token
def get_two_factor_status(token):
    try:
        user_data = decode_jwt_token(token)

        user = (
            supabase.table("users")
            .select("two_factor_auth, totp_secret")
            .eq("id", user_data["user_id"])
            .execute()
        )

        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        user_record = user.data[0]

        return (
            jsonify(
                {
                    "two_factor_auth": user_record.get("two_factor_auth", False),
                    "status": "success",
                }
            ),
            200,
        )

    except Exception as e:
        logging.error(
            f"Error in GET api/admin/settings/two-factor-auth/status: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/change-profile-picture", methods=["POST"])
@require_bearer_token
def change_profile_picture(token):
    try:
        user_data = decode_jwt_token(token)

        if "profile_picture" not in request.files:
            return (
                jsonify({"error": "No profile picture provided", "status": "error"}),
                400,
            )

        file = request.files["profile_picture"]

        if file.filename == "":
            return (
                jsonify({"error": "No profile picture selected", "status": "error"}),
                400,
            )
        allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
        if (
            not "." in file.filename
            or file.filename.rsplit(".", 1)[1].lower() not in allowed_extensions
        ):
            return (
                jsonify(
                    {
                        "error": "Invalid file type. Only PNG, JPG, JPEG, GIF, WEBP allowed",
                        "status": "error",
                    }
                ),
                400,
            )

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"

        file_content = file.read()
        profile_url = save_image_to_s3(
            io.BytesIO(file_content), unique_filename, file.content_type
        )
        if profile_url["status"] == "success":
            supabase.table("users").update(
                {
                    "profile_picture_url": profile_url["url"],
                    "profile_picture": unique_filename,
                }
            ).eq("id", user_data["user_id"]).execute()
            return (
                jsonify(
                    {
                        "message": "Profile picture changed successfully",
                        "status": "success",
                    }
                ),
                200,
            )

        else:
            return jsonify({"error": profile_url["message"], "status": "error"}), 500

    except Exception as e:
        logging.error(
            f"Error in POST api/admin/settings/change-profile-picture: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/delete-profile-picture", methods=["DELETE"])
@require_bearer_token
def delete_profile_picture(token):
    try:
        user_data = decode_jwt_token(token)
        user = (
            supabase.table("users")
            .select("profile_picture")
            .eq("id", user_data["user_id"])
            .execute()
        )
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404
        profile_picture = user.data[0]["profile_picture"]
        if profile_picture:
            delete_image_status = delete_image_from_s3(profile_picture)
            if delete_image_status["status"] == "error":
                return (
                    jsonify(
                        {"error": delete_image_status["message"], "status": "error"}
                    ),
                    500,
                )
            supabase.table("users").update(
                {"profile_picture": None, "profile_picture_url": None}
            ).eq("id", user_data["user_id"]).execute()
            return (
                jsonify(
                    {
                        "message": "Profile picture deleted successfully",
                        "status": "success",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify({"message": "No profile picture found", "status": "error"}),
                404,
            )
    except Exception as e:
        logging.error(
            f"Error in GET api/admin/settings/delete-profile-picture: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get-profile-picture", methods=["GET"])
@require_bearer_token
def get_profile_picture(token):
    try:
        user_data = decode_jwt_token(token)
        user = (
            supabase.table("users")
            .select("profile_picture_url")
            .eq("id", user_data["user_id"])
            .execute()
        )
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404
        profile_picture_url = user.data[0]["profile_picture_url"]
        if profile_picture_url:
            return (
                jsonify(
                    {"profile_picture_url": profile_picture_url, "status": "success"}
                ),
                200,
            )
        else:
            return (
                jsonify({"message": "No profile picture found", "status": "error"}),
                404,
            )
    except Exception as e:
        logging.error(f"Error in GET api/admin/settings/get-profile-picture: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/change-password", methods=["POST"])
@require_bearer_token
def change_password(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        if not data.get("old_password"):
            return (
                jsonify({"message": "Old password is required", "status": "error"}),
                400,
            )
        if not data.get("new_password"):
            return (
                jsonify({"message": "New password is required", "status": "error"}),
                400,
            )
        user = (
            supabase.table("users")
            .select("password")
            .eq("id", user_data["user_id"])
            .execute()
        )
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404
        if not verify_password(data["old_password"], user.data[0]["password"]):
            return jsonify({"message": "Invalid old password", "status": "error"}), 400
        supabase.table("users").update(
            {"password": hash_password(data["new_password"])}
        ).eq("id", user_data["user_id"]).execute()
        return (
            jsonify({"message": "Password changed successfully", "status": "success"}),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/settings/change-password: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/change-email-initiate", methods=["POST"])
@require_bearer_token
def change_email_initiate(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        if not data.get("new_email"):
            return (
                jsonify({"message": "New email is required", "status": "error"}),
                400,
            )
        if data["new_email"] == user_data["email"]:
            return (
                jsonify(
                    {
                        "message": "New email is the same as the current email",
                        "status": "error",
                    }
                ),
                400,
            )
        check_if_email_exists = (
            supabase.table("users")
            .select("email")
            .eq("email", data["new_email"])
            .execute()
        )
        if check_if_email_exists.data:
            return (
                jsonify({"message": "Email already exists", "status": "error"}),
                400,
            )
        verification_code = generate_verification_code()
        expiration_time = (datetime.now() + timedelta(minutes=5)).isoformat()
        supabase.table("users").update(
            {
                "verification_code": verification_code,
                "verification_code_expires_at": expiration_time,
            }
        ).eq("id", user_data["user_id"]).execute()
        status = send_email(
            "Email Verification Code",
            [data["new_email"]],
            f"Your email verification code is {verification_code}",
        )
        logging.info(f"Email change process initiated for user {user_data['email']}")
        return (
            jsonify(
                {
                    "message": "Email change process initiated, please check your email for the verification code",
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/settings/change-email: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/change-email/verify", methods=["POST"])
@require_bearer_token
def verify_change_email(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        if not data.get("new_email"):
            return (
                jsonify({"message": "New email is required", "status": "error"}),
                400,
            )
        if not data.get("code"):
            return (
                jsonify(
                    {"message": "Verification code is required", "status": "error"}
                ),
                400,
            )
        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        if user.data[0]["email"] == data["new_email"]:
            return (
                jsonify(
                    {
                        "message": "New email is the same as the current email",
                        "status": "error",
                    }
                ),
                400,
            )
        check_if_email_exists = (
            supabase.table("users")
            .select("email")
            .eq("email", data["new_email"])
            .execute()
        )
        if check_if_email_exists.data:
            return (
                jsonify({"message": "Email already exists", "status": "error"}),
                400,
            )
        if not user.data[0].get("verification_code"):
            return (
                jsonify(
                    {
                        "message": "No verification code request found. Please initiate email change first",
                        "status": "error",
                    }
                ),
                400,
            )
        if not user.data[0].get("verification_code_expires_at"):
            return (
                jsonify(
                    {
                        "message": "Verification code expired, request a new one",
                        "status": "error",
                    }
                ),
                400,
            )
        if (
            datetime.fromisoformat(user.data[0]["verification_code_expires_at"])
            < datetime.now()
        ):
            return (
                jsonify(
                    {
                        "message": "Verification code expired, request a new one",
                        "status": "error",
                    }
                ),
                400,
            )
        if user.data[0]["verification_code"] != data["code"]:
            return (
                jsonify({"message": "Invalid verification code", "status": "error"}),
                400,
            )
        business = (
            supabase.table("businesses")
            .select("customer_id")
            .eq("admin_id", user_data["user_id"])
            .execute()
        )
        if business.data[0]["customer_id"]:
            modify_customer_email(business.data[0]["customer_id"], data["new_email"])

        supabase.table("users").update(
            {
                "email": data["new_email"],
                "verification_code": None,
                "verification_code_expires_at": None,
            }
        ).eq("id", user_data["user_id"]).execute()
        insert_notification(
            user_data["user_id"],
            f"Email changed successfully to {data['new_email']}",
            "others",
        )

        logging.info(
            f"Email changed successfully for user {user.data[0]['email']} to {data['new_email']}"
        )
        return (
            jsonify({"message": "Email changed successfully", "status": "success"}),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/settings/change-email/verify: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/update-permissions", methods=["POST"])
@require_bearer_token
def update_permissions(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        email = data.get("email")
        position = data.get("position")
        status = data.get("status")

        if not email:
            return (
                jsonify({"message": "Email is required", "status": "error"}),
                400,
            )
        if not position:
            return (
                jsonify({"message": "Position is required", "status": "error"}),
                400,
            )

        checking_if_user_exists = (
            supabase.table("users")
            .select("status, role_id")
            .eq("email", email)
            .execute()
        )
        if not checking_if_user_exists.data:
            return (
                jsonify({"message": "User not found", "status": "error"}),
                404,
            )
        if checking_if_user_exists.data[0]["role_id"] in [1, 2]:
            return (
                jsonify(
                    {
                        "message": "You cannot update the permissions of this user",
                        "status": "error",
                    }
                ),
                400,
            )
        if checking_if_user_exists.data[0]["status"] in [2, 3, 4]:
            return jsonify(
                {
                    "message": "You cannot update the permissions of this user",
                    "status": "error",
                }
            )

        role_id = None
        if status == True:
            role_id = 8
        else:
            if position == "manager":
                role_id = 4
            else:
                role_id = 3

        check_admin_role = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if check_admin_role.data[0]["role_id"] not in [1, 2]:
            return (
                jsonify({"message": "Unauthorized access", "status": "error"}),
                400,
            )
        user = supabase.table("users").select("*").eq("email", data["email"]).execute()
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404
        supabase.table("users").update({"role_id": role_id}).eq(
            "id", user.data[0]["id"]
        ).execute()
        return (
            jsonify(
                {"message": "Permissions updated successfully", "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/settings/update-permissions: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


def init_settings_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/admin/settings")
