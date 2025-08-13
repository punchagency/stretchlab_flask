from flask import request, jsonify, Blueprint
from ..utils.middleware import require_bearer_token
from ..utils.utils import (
    decode_jwt_token,
    generate_random_password,
    clubready_admin_login,
    reverse_hash_credentials,
)
from ..utils.mail import send_email
from ..database.database import (
    get_employee_ownwer,
    get_owner_robot_automation_notes,
    get_owner_robot_automation_unlogged,
)
from ..utils.dashboard import get_start_and_end_date
import logging
from ..payment.stripe_utils import retrieve_payment_method, create_subscription
from datetime import datetime, timedelta
from ..utils.robot import create_s3_bucket, create_user_rule, update_user_rule_schedule
from ..notification import insert_notification
import json

routes = Blueprint("admin", __name__)


@routes.route("/invite-user", methods=["POST"])
@require_bearer_token
def invite_user(token):
    try:
        user_data = decode_jwt_token(token)
        check_user_exists_and_is_admin = (
            supabase.table("users")
            .select("*, roles(name)")
            .eq("id", user_data["user_id"])
            .in_("role_id", [1, 2, 4])
            .execute()
        )
        if not check_user_exists_and_is_admin.data:
            return (
                jsonify({"message": "User is not an admin", "status": "error"}),
                401,
            )
        check_subscription = (
            supabase.table("businesses")
            .select("payment_id,note_taking_subscription_id")
            .eq("username", check_user_exists_and_is_admin.data[0]["username"])
            .execute()
        )
        if (
            not check_subscription.data[0]["payment_id"]
            and check_user_exists_and_is_admin.data[0]["role_id"] != 1
        ):
            return (
                jsonify(
                    {
                        "message": "payment details needed",
                        "payment_id": False,
                        "status": "warning",
                    }
                ),
                402,
            )
        data = request.get_json()

        if (
            not check_subscription.data[0]["note_taking_subscription_id"]
            and not data["proceed"]
            and check_user_exists_and_is_admin.data[0]["role_id"] != 1
        ):
            payment_method = retrieve_payment_method(
                check_subscription.data[0]["payment_id"]
            )
            print(payment_method, "payment_method")
            paymentinfo = {
                "brand": payment_method.card.brand,
                "last4": payment_method.card.last4,
                "exp_month": payment_method.card.exp_month,
                "exp_year": payment_method.card.exp_year,
                "country": payment_method.card.country,
                "name": payment_method.billing_details.name,
                "email": payment_method.billing_details.email,
            }
            return (
                jsonify(
                    {
                        "message": "note taking subscription needed",
                        "payment_id": True,
                        "payment_info": paymentinfo,
                        "status": "warning",
                    }
                ),
                402,
            )

        email = data.get("email")
        password, hashed_password = generate_random_password()

        check_user_non_flexologist = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .neq("role_id", 3)
            .execute()
        )
        if check_user_non_flexologist.data:
            return (
                jsonify({"message": "User is not a flexologist", "status": "warning"}),
                409,
            )
        check_user_active = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .eq("status", 1)
            .eq("role_id", 3)
            .execute()
        )
        if check_user_active.data:
            return jsonify({"message": "User already active", "status": "warning"}), 409

        check_user_disabled = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .eq("status", 2)
            .eq("role_id", 3)
            .execute()
        )
        if check_user_disabled.data:
            return (
                jsonify(
                    {
                        "message": "User already disabled, grant access to continue",
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
            .eq("role_id", 3)
            .execute()
        )
        if check_user_invited.data:
            send_email(
                "Invitation to Stretchnote Note taking app",
                [email],
                None,
                f"<html><body><p>You have been invited to the <a href='https://www.stretchnote.com/login'>Stretchnote Note taking app</a>. These are your login credentials:</p><p>Email: {email}</p><p>Password: {password}</p> <p>Here is the link to the app: <a href='https://www.stretchnote.com/login'>Stretchnote Note taking app</a></p></body></html>",
            )

            return (
                jsonify(
                    {
                        "message": "User previously invited. Resent email, check email for credentials",
                        "status": "success",
                    }
                ),
                200,
            )
        check_user_pending = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .in_("status", [4, 5])
            .eq("role_id", 3)
            .execute()
        )
        if check_user_pending.data:
            send_email(
                "Please Complete your Registration",
                [email],
                None,
                f"<html><body><p>Please complete your registration by clicking the link below:</p><p><a href='https://www.stretchnote.com/login'>Complete Registration</a></p>body></html>",
            )

            return (
                jsonify(
                    {
                        "message": "User is pending, a nudging email has been sent",
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
                    "status": 3,
                    "role_id": 3,
                    "username": check_user_exists_and_is_admin.data[0]["username"],
                    "admin_id": check_user_exists_and_is_admin.data[0]["admin_id"],
                    "password": hashed_password,
                    "invited_at": datetime.now().isoformat(),
                }
            )
            .execute()
        )
        new_user = new_user.data[0]
        if new_user:
            status = send_email(
                "Invitation to Stretchnote Note taking app",
                [email],
                None,
                f"<html><body><p>You have been invited to the <a href='https://www.stretchnote.com/login'>Stretchnote Note taking app</a>. These are your login credentials:</p><p>Email: {email}</p><p>Password: {password}</p> <p>Here is the link to the app: <a href='https://www.stretchnote.com/login'>Stretchnote Note taking app</a></p></body></html>",
            )
            if status["success"]:
                return (
                    jsonify(
                        {"message": "User invited successfully", "status": "success"}
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
        logging.error(f"Error in POST api/admin/process/invite-user: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/update-user-status", methods=["POST"])
@require_bearer_token
def update_user_status(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        email = data.get("email")
        status = data.get("status")
        supabase.table("users").update({"status": status}).eq("email", email).eq(
            "admin_id", user_data["user_id"]
        ).execute()
        insert_notification(
            user_data["user_id"],
            f"Your chnaged the status of {email} to {status == 1 and 'active' or 'disabled'}",
            "note taking",
        )
        return (
            jsonify(
                {
                    "message": f"User access {status == 1 and 'granted' or 'revoked'} successfully",
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/process/update-user-status: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get-users", methods=["GET"])
@require_bearer_token
def get_users(token):
    try:
        user_data = decode_jwt_token(token)
        if user_data["role_id"] == 1:
            employees_from_airtable = get_employee_ownwer()
            employees_from_supabase = (
                supabase.table("users")
                .select("*")
                .eq("username", user_data["username"])
                .neq("role_id", 1)
                .execute()
            )
            employees_from_supabase = employees_from_supabase.data
            for employee in employees_from_airtable:
                matching_employee = next(
                    (
                        e
                        for e in employees_from_supabase
                        if e["email"] == employee["email"]
                    ),
                    None,
                )
                if not matching_employee:
                    employee["status"] = None
                    employee["invited_at"] = None
                    employees_from_supabase.append(employee)
            employees = employees_from_supabase
        else:
            employees = user = (
                supabase.table("users")
                .select("*")
                .eq("username", user_data["username"])
                .neq("role_id", 2)
                .execute()
            )
            employees = user.data
        return jsonify({"users": employees, "status": "success"}), 200
    except Exception as e:
        logging.error(f"Error in GET /admin/get-users: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/validate-login", methods=["POST"])
@require_bearer_token
def validate_login(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()

        validate_login = clubready_admin_login(data)
        print(user_data["user_id"], "user info")
        if validate_login["status"]:
            supabase.table("users").update(
                {
                    "clubready_username": data["username"],
                    "clubready_password": validate_login["hashed_password"],
                }
            ).eq("id", user_data["user_id"]).execute()
            return (
                jsonify(
                    {
                        "message": validate_login["message"],
                        "status": validate_login["status"],
                        "locations": validate_login["locations"],
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "message": validate_login["message"],
                        "status": validate_login["status"],
                    },
                ),
                200,
            )

    except Exception as e:
        logging.error(f"Error in POST api/admin/process/validate-login: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/save-robot-config", methods=["POST"])
@require_bearer_token
def save_robot_config(token):
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

        check_subscription = (
            supabase.table("businesses")
            .select("payment_id,robot_process_automation_subscription_id, customer_id")
            .eq("admin_id", user_data["user_id"])
            .execute()
        )
        print(check_user_exists_and_is_admin.data[0])
        if (
            not check_subscription.data[0]["payment_id"]
            and check_user_exists_and_is_admin.data[0]["role_id"] != 1
        ):
            return (
                jsonify(
                    {
                        "message": "payment details needed",
                        "payment_id": False,
                        "status": "warning",
                    }
                ),
                402,
            )
        data = request.get_json()
        if (
            not check_subscription.data[0]["robot_process_automation_subscription_id"]
            and not data["proceed"]
            and check_user_exists_and_is_admin.data[0]["role_id"] != 1
        ):
            payment_method = retrieve_payment_method(
                check_subscription.data[0]["payment_id"]
            )
            print(payment_method, "payment_method")
            paymentinfo = {
                "brand": payment_method.card.brand,
                "last4": payment_method.card.last4,
                "exp_month": payment_method.card.exp_month,
                "exp_year": payment_method.card.exp_year,
                "country": payment_method.card.country,
                "name": payment_method.billing_details.name,
                "email": payment_method.billing_details.email,
            }
            return (
                jsonify(
                    {
                        "message": "Add subscription to this card to proceed?",
                        "payment_id": True,
                        "payment_info": paymentinfo,
                        "status": "warning",
                    }
                ),
                402,
            )

        get_price = (
            supabase.table("prices").select("price_id").eq("type", "robot").execute()
        )
        check_if_robot_exists = (
            supabase.table("robot_process_automation_config")
            .select("*")
            .eq("name", f"{user_data['username']}-robot")
            .execute()
        )
        if check_if_robot_exists.data:
            return (
                jsonify({"message": "Robot already exists", "status": "error"}),
                400,
            )

        subscription = create_subscription(
            check_subscription.data[0]["customer_id"],
            get_price.data[0]["price_id"],
            quantity=data["numberOfStudioLocations"],
        )
        if subscription["success"] == False:
            return (
                jsonify({"message": "Subscription failed", "status": "error"}),
                400,
            )

        bucket_name = create_s3_bucket(user_data["username"], user_data["user_id"])
        rule_arn = create_user_rule(
            username=user_data["username"],
            role_arn="arn:aws:iam::886351739165:role/service-role/Amazon_EventBridge_Invoke_ECS_2143115626",
            bucket_name=bucket_name,
        )
        config = (
            supabase.table("robot_process_automation_config")
            .insert(
                {
                    "name": f"{user_data['username']}-robot",
                    "number_of_locations": data["numberOfStudioLocations"],
                    "selected_locations": json.dumps(data["selectedStudioLocations"]),
                    "locations": json.dumps(data["studioLocations"]),
                    "unlogged_booking": True,
                    "run_time": "07:30",
                    "rule_arn": rule_arn,
                    "bucket_name": bucket_name,
                    "active": True,
                    "admin_id": user_data["user_id"],
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )
            .execute()
        )
        if config.data:
            supabase.table("businesses").update(
                {
                    "locations": json.dumps(data["studioLocations"]),
                }
            ).eq("admin_id", user_data["user_id"]).execute()

            if check_user_exists_and_is_admin.data[0]["role_id"] == 1:
                supabase.table("users").update(
                    {
                        "status": 1,
                    }
                ).eq("id", user_data["user_id"]).execute()
                insert_notification(
                    user_data["user_id"],
                    f"Robot config was created",
                    "robot automation",
                )
                return (
                    jsonify(
                        {
                            "message": "Robot config saved successfully",
                            "status": "success",
                        }
                    ),
                    200,
                )

            supabase.table("businesses").update(
                {
                    "robot_process_automation_subscription_id": subscription[
                        "subscription_id"
                    ],
                    "robot_process_automation_subscription_status": subscription[
                        "status"
                    ],
                    "robot_process_automation_active": True,
                }
            ).eq("admin_id", user_data["user_id"]).execute()
            supabase.table("users").update(
                {
                    "status": 1,
                }
            ).eq("id", user_data["user_id"]).execute()
            insert_notification(
                user_data["user_id"],
                f"Robot config was created",
                "robot automation",
            )

            return (
                jsonify(
                    {
                        "message": "Robot config saved successfully",
                        "status": "success",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify({"message": "Robot config save failed", "status": "error"}),
                400,
            )
    except Exception as e:
        logging.error(f"Error in POST api/admin/process/save-robot-config: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get-robot-config", methods=["GET"])
@require_bearer_token
def get_robot_config(token):
    try:
        user_data = decode_jwt_token(token)
        check_user_exists_and_is_admin = (
            supabase.table("users")
            .select("*")
            .eq("id", user_data["user_id"])
            .in_("role_id", [1, 2, 4])
            .execute()
        )
        print(check_user_exists_and_is_admin.data, "check_user_exists_and_is_admin")

        if not check_user_exists_and_is_admin.data:
            return (
                jsonify({"message": "User is not an admin", "status": "error"}),
                401,
            )
        robot_config = (
            supabase.table("robot_process_automation_config")
            .select("*, users(clubready_username,clubready_password)")
            .eq("admin_id", check_user_exists_and_is_admin.data[0]["admin_id"])
            .execute()
        )

        if robot_config.data:
            get_rpa_sub_status = (
                supabase.table("businesses")
                .select("robot_process_automation_active")
                .eq("admin_id", check_user_exists_and_is_admin.data[0]["admin_id"])
                .execute()
            )

            password = reverse_hash_credentials(
                robot_config.data[0]["users"]["clubready_username"],
                robot_config.data[0]["users"]["clubready_password"],
            )
            robot_config_data = {
                **robot_config.data[0],
                "users": {
                    **robot_config.data[0]["users"],
                    "clubready_password": password,
                },
                "rpa_sub_status": get_rpa_sub_status.data[0][
                    "robot_process_automation_active"
                ],
            }
            return (
                jsonify({"robot_config": robot_config_data, "config": True}),
                200,
            )
        else:
            return jsonify({"message": "No robot config found", "config": False}), 200
    except Exception as e:
        logging.error(f"Error in GET api/admin/process/get-robot-config: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get-rpa-history/<int:config_id>", methods=["GET"])
@require_bearer_token
def get_rpa_history(token, config_id):
    try:
        user_data = decode_jwt_token(token)
        duration = request.args.get("duration", "this_year")

        check_user_exists_and_is_admin = (
            supabase.table("users")
            .select("*")
            .eq("id", user_data["user_id"])
            .in_("role_id", [1, 2, 4])
            .execute()
        )
        if not check_user_exists_and_is_admin.data:
            return (
                jsonify({"message": "User is not an admin", "status": "error"}),
                401,
            )

        if duration == "custom":
            start_date_str = request.args.get("start_date")
            end_date_str = request.args.get("end_date")
            if not start_date_str or not end_date_str:
                return (
                    jsonify(
                        {"error": "Start and end date are required", "status": "error"}
                    ),
                    400,
                )
            start_date, end_date = get_start_and_end_date(
                duration, start_date_str, end_date_str
            )

        else:
            start_date, end_date = get_start_and_end_date(duration)

        # if check_user_exists_and_is_admin.data[0]["role_id"] == 1:
        #     rpa_history = get_owner_robot_automation_notes(start_date, end_date)
        #     rpa_unlogged_history = get_owner_robot_automation_unlogged(
        #         start_date, end_date
        #     )
        # else:

        rpa_history = (
            supabase.table("robot_process_automation_notes_records")
            .select("*")
            .eq("config_id", config_id)
            .gte("appointment_date", start_date)
            .lt("appointment_date", end_date)
            .execute()
        )
        rpa_unlogged_history = (
            supabase.table("robot_process_automation_unlogged_booking_records")
            .select("*")
            .eq("config_id", config_id)
            .gte("appointment_date", start_date)
            .lt("appointment_date", end_date)
            .execute()
        )
        rpa_history = rpa_history.data
        rpa_unlogged_history = rpa_unlogged_history.data

        return (
            jsonify(
                {
                    "rpa_history": rpa_history,
                    "rpa_unlogged_history": rpa_unlogged_history,
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in GET api/admin/process/get-rpa-history: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/update-robot-config", methods=["POST"])
@require_bearer_token
def update_robot_config(token):
    try:
        user_data = decode_jwt_token(token)
        check_user_exists_and_is_admin = (
            supabase.table("users")
            .select("*")
            .eq("id", user_data["user_id"])
            .in_("role_id", [1, 2])
            .execute()
        )
        if not check_user_exists_and_is_admin.data:
            return (
                jsonify({"message": "User is not an admin", "status": "error"}),
                401,
            )
        get_robot_config = (
            supabase.table("robot_process_automation_config")
            .select("*")
            .eq("admin_id", check_user_exists_and_is_admin.data[0]["id"])
            .execute()
        )
        if not get_robot_config.data:
            return jsonify({"message": "No robot config found", "status": "error"}), 400
        data = request.get_json()
        rule_arn = update_user_rule_schedule(
            username=check_user_exists_and_is_admin.data[0]["username"],
        )

        supabase.table("robot_process_automation_config").update(
            {
                "rule_arn": rule_arn,
                "locations": json.dumps(data["studioLocations"]),
                "selected_locations": json.dumps(data["selectedStudioLocations"]),
                "number_of_locations": data["numberOfStudioLocations"],
                "unlogged_booking": True,
                "updated_at": datetime.now().isoformat(),
            }
        ).eq("id", data["id"]).execute()
        insert_notification(
            user_data["user_id"],
            f"Robot config was updated",
            "robot automation",
        )
        return (
            jsonify(
                {"message": "Robot config updated successfully", "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/process/update-robot-config: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/change-status-robot", methods=["POST"])
@require_bearer_token
def change_status_robot(token):
    try:
        user_data = decode_jwt_token(token)
        check_user_exists_and_is_admin = (
            supabase.table("users")
            .select("*")
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
        rule_arn = update_user_rule_schedule(
            username=check_user_exists_and_is_admin.data[0]["username"],
            state=data["status"],
        )
        if rule_arn:
            supabase.table("robot_process_automation_config").update(
                {"active": True if data["status"] == "ENABLED" else False}
            ).eq("admin_id", check_user_exists_and_is_admin.data[0]["id"]).execute()

        insert_notification(
            user_data["user_id"],
            f"Robot config was {data['status'].lower()}",
            "robot automation",
        )

        return (
            jsonify(
                {
                    "message": f"Robot {data['status'].lower()} successfully",
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/process/change-status-robot: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/update-settings", methods=["POST"])
@require_bearer_token
def update_settings(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        return (
            jsonify({"message": "Settings updated successfully", "status": "success"}),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/process/update-settings: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


def init_admin_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/admin/process")
