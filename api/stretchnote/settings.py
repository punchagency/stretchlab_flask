from flask import Blueprint, request, jsonify
from ..utils.utils import decode_jwt_token, reverse_hash_credentials, clubready_login
from ..utils.middleware import require_bearer_token
import logging
import json
import uuid

routes = Blueprint("note_settings", __name__)


@routes.route("/get-clubready-details", methods=["GET"])
@require_bearer_token
def get_clubready_details(token):
    try:
        user_data = decode_jwt_token(token)
        account_id = request.args.get("account_id", None)
        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        if account_id:
            other_accounts = (
                json.loads(user.data[0]["other_clubready_accounts"])
                if user.data[0]["other_clubready_accounts"]
                else None
            )
            for account in other_accounts:
                if account["id"] == account_id:
                    clubready_username = account["username"]
                    clubready_password = account["password"]
                    break
        else:
            clubready_username = user.data[0]["clubready_username"]
            clubready_password = user.data[0]["clubready_password"]
        clubready_password = reverse_hash_credentials(
            clubready_username, clubready_password
        )
        return (
            jsonify(
                {
                    "clubready_username": clubready_username,
                    "clubready_password": clubready_password,
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(
            f"Error in GET api/stretchnote/settings/get-clubready-details: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/update-clubready-details", methods=["POST"])
@require_bearer_token
def update_clubready_details(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        if not data.get("username"):
            return (
                jsonify(
                    {"message": "Clubready username is required", "status": "error"}
                ),
                400,
            )
        if not data.get("password"):
            return (
                jsonify(
                    {"message": "Clubready password is required", "status": "error"}
                ),
                400,
            )

        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        validate_clubready = clubready_login(data)
        if not validate_clubready["status"]:
            return (
                jsonify({"message": validate_clubready["message"], "status": "error"}),
                400,
            )

        account_id = data.get("account_id", None)
        if account_id:
            other_accounts = (
                json.loads(user.data[0]["other_clubready_accounts"])
                if user.data[0]["other_clubready_accounts"]
                else None
            )
            if not other_accounts:
                return (
                    jsonify(
                        {
                            "message": "No other clubready accounts found",
                            "status": "error",
                        }
                    ),
                    404,
                )
            for account in other_accounts:
                if account["id"] == account_id:
                    account["username"] = data["username"]
                    account["password"] = validate_clubready["hashed_password"]
                    account["location_id"] = validate_clubready["location_id"]
                    account["user_id"] = validate_clubready["user_id"]
                    account["full_name"] = validate_clubready["full_name"]
                    break
            other_accounts = json.dumps(other_accounts)
            supabase.table("users").update(
                {
                    "other_clubready_accounts": other_accounts,
                }
            ).eq("id", user_data["user_id"]).execute()
        else:
            clubready_username = data["username"]
            clubready_password = validate_clubready["hashed_password"]
            location = validate_clubready["location_id"]
            user_id = validate_clubready["user_id"]
            full_name = validate_clubready["full_name"]

            supabase.table("users").update(
                {
                    "clubready_username": clubready_username,
                    "clubready_password": clubready_password,
                    "clubready_location_id": location,
                    "clubready_user_id": user_id,
                    "full_name": full_name,
                }
            ).eq("id", user_data["user_id"]).execute()

        logging.info(
            f"Clubready details updated successfully for user {user_data['email']}"
        )
        return (
            jsonify(
                {
                    "message": "Clubready details updated successfully",
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(
            f"Error in POST api/stretchnote/settings/update-clubready-details: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/update-profile-name", methods=["POST"])
@require_bearer_token
def update_profile_name(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        if not data.get("profile_name"):
            return (
                jsonify({"message": "A new name is required", "status": "error"}),
                400,
            )
        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        account_id = data.get("account_id", None)
        if account_id:
            other_accounts = (
                json.loads(user.data[0]["other_clubready_accounts"])
                if user.data[0]["other_clubready_accounts"]
                else None
            )
            if not other_accounts:
                return (
                    jsonify(
                        {
                            "message": "No other clubready accounts found",
                            "status": "error",
                        }
                    ),
                    404,
                )
            for account in other_accounts:
                if account["id"] == account_id:
                    account["full_name"] = data["profile_name"]
                    break
            other_accounts = json.dumps(other_accounts)
            supabase.table("users").update(
                {
                    "other_clubready_accounts": other_accounts,
                }
            ).eq("id", user_data["user_id"]).execute()
        else:
            full_name = data["profile_name"]

            supabase.table("users").update(
                {
                    "full_name": full_name,
                }
            ).eq("id", user_data["user_id"]).execute()

        logging.info(f"Profile name updated successfully for user {user_data['email']}")
        return (
            jsonify(
                {
                    "message": "Display name updated successfully",
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(
            f"Error in POST api/stretchnote/settings/update-profile-name: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/add-clubready-account", methods=["POST"])
@require_bearer_token
def add_clubready_account(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        if not data.get("username"):
            return (
                jsonify(
                    {"message": "Clubready username is required", "status": "error"}
                ),
                400,
            )
        if not data.get("password"):
            return (
                jsonify(
                    {"message": "Clubready password is required", "status": "error"}
                ),
                400,
            )

        check_user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not check_user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        if check_user.data[0]["clubready_username"].lower() == data["username"].lower():
            return (
                jsonify(
                    {"message": "Clubready username already exists", "status": "error"}
                ),
                400,
            )

        if check_user.data[0]["other_clubready_accounts"]:
            other_accounts = json.loads(check_user.data[0]["other_clubready_accounts"])
            for account in other_accounts:
                if account["username"].lower() == data["username"].lower():
                    return (
                        jsonify(
                            {
                                "message": "Clubready username already exists",
                                "status": "error",
                            }
                        ),
                        400,
                    )

        validate_clubready = clubready_login(data)
        if not validate_clubready["status"]:
            return (
                jsonify({"message": validate_clubready["message"], "status": "error"}),
                400,
            )

        data_to_add = {
            "id": str(uuid.uuid4()),
            "username": data["username"],
            "password": validate_clubready["hashed_password"],
            "location_id": validate_clubready["location_id"],
            "user_id": validate_clubready["user_id"],
            "full_name": validate_clubready["full_name"],
            "active": False,
        }

        get_accounts = (
            supabase.table("users")
            .select("other_clubready_accounts")
            .eq("id", user_data["user_id"])
            .execute()
        )
        if get_accounts.data[0]["other_clubready_accounts"]:
            other_accounts = json.loads(
                get_accounts.data[0]["other_clubready_accounts"]
            )
        else:
            other_accounts = []
        other_accounts.append(data_to_add)
        other_accounts = json.dumps(other_accounts)

        supabase.table("users").update(
            {
                "other_clubready_accounts": other_accounts,
            }
        ).eq("id", user_data["user_id"]).execute()

        logging.info(
            f"Clubready account added successfully for user {user_data['email']}"
        )
        return (
            jsonify(
                {"message": "Clubready account added successfully", "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(
            f"Error in POST api/stretchnote/settings/add-clubready-account: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get-clubready-accounts", methods=["GET"])
@require_bearer_token
def get_clubready_accounts(token):
    try:
        user_data = decode_jwt_token(token)
        check_user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not check_user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404
        other_accounts = (
            json.loads(check_user.data[0]["other_clubready_accounts"])
            if check_user.data[0]["other_clubready_accounts"]
            else []
        )
        if len(other_accounts) > 0:
            other_accounts = [
                {
                    "id": account["id"],
                    "name": account["full_name"],
                    "active": account["active"],
                    "username": account["username"],
                    "location_id": account["location_id"],
                    "user_id": account["user_id"],
                }
                for account in other_accounts
            ]
        other_accounts.insert(
            0,
            {
                "id": None,
                "name": check_user.data[0]["full_name"],
                "active": True,
                "username": check_user.data[0]["clubready_username"],
                "location_id": check_user.data[0]["clubready_location_id"],
                "user_id": check_user.data[0]["clubready_user_id"],
            },
        )
        return jsonify({"accounts": other_accounts, "status": "success"}), 200
    except Exception as e:
        logging.error(
            f"Error in GET api/stretchnote/settings/get-clubready-accounts: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/delete-clubready-account", methods=["POST"])
@require_bearer_token
def delete_clubready_account(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        if not data.get("account_id"):
            return (
                jsonify({"message": "Account ID is required", "status": "error"}),
                400,
            )

        check_user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not check_user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404

        other_accounts = (
            json.loads(check_user.data[0]["other_clubready_accounts"])
            if check_user.data[0]["other_clubready_accounts"]
            else None
        )
        if other_accounts:
            for account in other_accounts:
                if account["id"] == data["account_id"]:
                    other_accounts.remove(account)
                    break
            other_accounts = json.dumps(other_accounts)
            supabase.table("users").update(
                {"other_clubready_accounts": other_accounts}
            ).eq("id", user_data["user_id"]).execute()
        return (
            jsonify(
                {
                    "message": "Clubready account deleted successfully",
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(
            f"Error in POST api/stretchnote/settings/delete-clubready-account: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


def init_note_settings_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/stretchnote/settings")
