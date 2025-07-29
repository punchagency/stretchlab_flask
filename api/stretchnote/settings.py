from flask import Blueprint, request, jsonify
from ..utils.utils import decode_jwt_token, reverse_hash_credentials, clubready_login
from ..utils.middleware import require_bearer_token
import logging

routes = Blueprint("note_settings", __name__)


@routes.route("/get-clubready-details", methods=["GET"])
@require_bearer_token
def get_clubready_details(token):
    try:
        user_data = decode_jwt_token(token)
        user = (
            supabase.table("users").select("*").eq("id", user_data["user_id"]).execute()
        )
        if not user.data:
            return jsonify({"message": "User not found", "status": "error"}), 404
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

        validate_clubready = clubready_login(data)
        if not validate_clubready["status"]:
            return (
                jsonify({"message": validate_clubready["message"], "status": "error"}),
                400,
            )

        supabase.table("users").update(
            {
                "clubready_username": data["username"],
                "clubready_password": validate_clubready["hashed_password"],
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


def init_note_settings_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/stretchnote/settings")
