from flask import Blueprint, request, jsonify
from ..utils.utils import (
    decode_jwt_token,
)
from ..utils.middleware import require_bearer_token
from ..payment.stripe_utils import (
    create_setup_intent,
    create_payment_method,
    get_subscription_details,
    cancel_subscription,
    restart_subscription,
)
import logging
from ..notification import insert_notification
from ..utils.robot import update_user_rule_schedule

routes = Blueprint("payment", __name__)


@routes.route("/create-setup-intent", methods=["GET"])
@require_bearer_token
def create_setup_intent_route(token):
    try:
        user_data = decode_jwt_token(token)
        role = request.args.get("role")
        get_customer = (
            supabase.table("businesses")
            .select("customer_id")
            .eq("admin_id", user_data["user_id"])
            .execute()
        )
        customer_id = get_customer.data[0]["customer_id"]
        setup_intent = create_setup_intent(customer_id)
        get_price = supabase.table("prices").select("*").eq("type", role).execute()
        return (
            jsonify(
                {
                    "clientSecret": setup_intent["client_secret"],
                    "price": get_price.data[0]["price"],
                    "status": "success",
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/payment/create-setup-intent: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/update-payment-method", methods=["POST"])
@require_bearer_token
def update_payment_id(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()

        payment_id = data.get("payment_id")

        get_customer = (
            supabase.table("businesses")
            .select("customer_id")
            .eq("admin_id", user_data["user_id"])
            .execute()
        )
        customer_id = get_customer.data[0]["customer_id"]

        result = create_payment_method(customer_id, payment_id)
        if result["status"]:
            supabase.table("businesses").update({"payment_id": payment_id}).eq(
                "admin_id", user_data["user_id"]
            ).execute()
            insert_notification(
                user_data["user_id"],
                f"Payment method was updated",
                "payment",
            )
            return (
                jsonify(
                    {
                        "message": "Payment method updated successfully",
                        "status": "success",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify({"message": result["message"], "status": "error"}),
                400,
            )
    except Exception as e:
        logging.error(f"Error in POST api/admin/payment/update-payment-id: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get-billing-history", methods=["GET"])
@require_bearer_token
def get_billing_history(token):
    try:
        user_data = decode_jwt_token(token)
        get_customer = (
            supabase.table("businesses")
            .select("*")
            .eq("admin_id", user_data["user_id"])
            .execute()
        )
        if not get_customer.data:
            return jsonify({"message": "No business found", "status": "error"}), 400
        admin_id = get_customer.data[0]["admin_id"]
        get_billing_history = (
            supabase.table("billing_history")
            .select("*")
            .eq("user_id", admin_id)
            .execute()
        )
        return (
            jsonify({"billing_history": get_billing_history.data, "status": "success"}),
            200,
        )
    except Exception as e:
        logging.error(f"Error in GET api/admin/payment/get-billing-history: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/get-subscriptions-details", methods=["GET"])
@require_bearer_token
def get_subscriptions_details(token):
    try:
        user_data = decode_jwt_token(token)
        get_customer = (
            supabase.table("businesses")
            .select("*")
            .eq("admin_id", user_data["user_id"])
            .execute()
        )
        if not get_customer.data:
            return jsonify({"message": "No business found", "status": "error"}), 400
        suscription_details = []
        if get_customer.data[0]["note_taking_subscription_id"]:
            note_taking_sub = get_customer.data[0]["note_taking_subscription_id"]
            note_taking_sub_details = get_subscription_details(note_taking_sub)
            data_to_send = {
                "price": note_taking_sub_details["items"]["data"][0]["price"][
                    "unit_amount"
                ],
                "currency": note_taking_sub_details["items"]["data"][0]["price"][
                    "currency"
                ],
                "quantity": note_taking_sub_details["items"]["data"][0]["quantity"],
                "interval": note_taking_sub_details["plan"]["interval"],
                "status": note_taking_sub_details["status"],
                "start_date": note_taking_sub_details["items"]["data"][0][
                    "current_period_start"
                ],
                "end_date": note_taking_sub_details["items"]["data"][0][
                    "current_period_end"
                ],
            }
            suscription_details.append(
                {
                    "note_taking": data_to_send,
                }
            )
        if get_customer.data[0]["robot_process_automation_subscription_id"]:
            robot_process_automation_sub = get_customer.data[0][
                "robot_process_automation_subscription_id"
            ]
            robot_process_automation_sub_details = get_subscription_details(
                robot_process_automation_sub
            )
            data_to_send = {
                "price": robot_process_automation_sub_details["items"]["data"][0][
                    "price"
                ]["unit_amount"],
                "currency": robot_process_automation_sub_details["items"]["data"][0][
                    "price"
                ]["currency"],
                "quantity": robot_process_automation_sub_details["items"]["data"][0][
                    "quantity"
                ],
                "interval": robot_process_automation_sub_details["plan"]["interval"],
                "status": robot_process_automation_sub_details["status"],
                "start_date": robot_process_automation_sub_details["items"]["data"][0][
                    "current_period_start"
                ],
                "end_date": robot_process_automation_sub_details["items"]["data"][0][
                    "current_period_end"
                ],
            }

            suscription_details.append(
                {
                    "robot_process_automation": data_to_send,
                }
            )

        return (
            jsonify(
                {"subscriptions_details": suscription_details, "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(
            f"Error in GET api/admin/payment/get-subscriptions-details: {str(e)}"
        )
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/cancel-subscription", methods=["POST"])
@require_bearer_token
def cancel_subscription_route(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        sub_type = data["type"]
        if sub_type == "note_taking":
            subscription_id = (
                supabase.table("businesses")
                .select("note_taking_subscription_id")
                .eq("admin_id", user_data["user_id"])
                .execute()
            )
            if subscription_id.data[0]["note_taking_subscription_id"]:
                cancel_subscription(
                    subscription_id.data[0]["note_taking_subscription_id"]
                )
                supabase.table("businesses").update({"note_taking_active": False}).eq(
                    "admin_id", user_data["user_id"]
                ).execute()
                insert_notification(
                    user_data["user_id"],
                    f"Note taking subscription was cancelled",
                    "payment",
                )
        elif sub_type == "robot_process_automation":
            subscription_id = (
                supabase.table("businesses")
                .select("robot_process_automation_subscription_id")
                .eq("admin_id", user_data["user_id"])
                .execute()
            )
            if subscription_id.data[0]["robot_process_automation_subscription_id"]:
                cancel_subscription(
                    subscription_id.data[0]["robot_process_automation_subscription_id"]
                )
                rule_arn = update_user_rule_schedule(
                    username=user_data["username"],
                    state="DISABLED",
                )
                if rule_arn:
                    supabase.table("robot_process_automation_config").update(
                        {"active": False}
                    ).eq("admin_id", user_data["user_id"]).execute()
                    supabase.table("businesses").update(
                        {"robot_process_automation_active": False}
                    ).eq("admin_id", user_data["user_id"]).execute()

                insert_notification(
                    user_data["user_id"],
                    f"Robot process automation subscription was cancelled",
                    "payment",
                )
        return (
            jsonify(
                {"message": "Subscription cancelled successfully", "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/payment/cancel-subscription: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@routes.route("/restart-subscription", methods=["POST"])
@require_bearer_token
def restart_subscription_route(token):
    try:
        user_data = decode_jwt_token(token)
        data = request.get_json()
        sub_type = data["type"]
        if sub_type == "note_taking":
            subscription_id = (
                supabase.table("businesses")
                .select("note_taking_subscription_id")
                .eq("admin_id", user_data["user_id"])
                .execute()
            )
            if subscription_id.data[0]["note_taking_subscription_id"]:
                result = restart_subscription(
                    subscription_id.data[0]["note_taking_subscription_id"]
                )
                if result["status"]:
                    supabase.table("businesses").update(
                        {
                            "note_taking_active": True,
                            "note_taking_subscription_id": result["subscription_id"],
                            "note_taking_subscription_status": result[
                                "subscription_status"
                            ],
                        }
                    ).eq("admin_id", user_data["user_id"]).execute()
                    insert_notification(
                        user_data["user_id"],
                        f"Note taking subscription was restarted",
                        "payment",
                    )
        elif sub_type == "robot_process_automation":
            subscription_id = (
                supabase.table("businesses")
                .select("robot_process_automation_subscription_id")
                .eq("admin_id", user_data["user_id"])
                .execute()
            )
            if subscription_id.data[0]["robot_process_automation_subscription_id"]:
                result = restart_subscription(
                    subscription_id.data[0]["robot_process_automation_subscription_id"]
                )
                if result["status"]:
                    rule_arn = update_user_rule_schedule(
                        username=user_data["username"],
                        state="ENABLED",
                    )
                    if rule_arn:
                        supabase.table("robot_process_automation_config").update(
                            {"active": True}
                        ).eq("admin_id", user_data["user_id"]).execute()
                        supabase.table("businesses").update(
                            {
                                "robot_process_automation_active": True,
                                "robot_process_automation_subscription_id": result[
                                    "subscription_id"
                                ],
                                "robot_process_automation_subscription_status": result[
                                    "subscription_status"
                                ],
                            }
                        ).eq("admin_id", user_data["user_id"]).execute()

                    insert_notification(
                        user_data["user_id"],
                        f"Robot process automation subscription was restarted",
                        "payment",
                    )
        return (
            jsonify(
                {"message": "Subscription restarted successfully", "status": "success"}
            ),
            200,
        )
    except Exception as e:
        logging.error(f"Error in POST api/admin/payment/restart-subscription: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


def init_payment_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/admin/payment")
