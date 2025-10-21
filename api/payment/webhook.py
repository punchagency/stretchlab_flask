from flask import Blueprint, request, jsonify
import stripe
from dotenv import load_dotenv
import os
from datetime import datetime
from ..utils.robot import update_user_rule_schedule

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

routes = Blueprint("payment_webhook", __name__)


@routes.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid webhook signature"}), 400
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400

    if event["type"] == "invoice.payment_succeeded":
        print("Invoice paid")
        invoice = event["data"]["object"]
        # subscription_id = invoice["subscription"]
        print(invoice)
        customer_id = invoice["customer"]
        amount_paid = invoice["amount_paid"] / 100
        print(
            f"Invoice paid for subscription: ${amount_paid} for customer {customer_id}"
        )
        get_user = (
            supabase.table("businesses")
            .select("admin_id")
            .eq("customer_id", customer_id)
            .execute()
        )
        supabase.table("billing_history").insert(
            {
                "user_id": get_user.data[0]["admin_id"],
                "amount": amount_paid,
                "invoice_id": invoice["id"],
                "subscription_id": invoice["subscription"],
                "invoice_url": invoice["hosted_invoice_url"],
                "invoice_pdf_url": invoice["invoice_pdf"],
                "status": invoice["status"],
                "created_at": datetime.now().isoformat(),
            }
        ).execute()

        get_rpa_subscription = (
            supabase.table("businesses")
            .select("robot_process_automation_subscription_id")
            .eq(
                "robot_process_automation_subscription_id",
                invoice["subscription"],
            )
            .execute()
        )
        if get_rpa_subscription.data:
            expires_at = datetime.fromtimestamp(
                invoice["lines"]["data"][0]["period"]["end"]
            ).isoformat()
            supabase.table("businesses").update(
                {
                    "robot_process_automation_active": True,
                    "robot_process_automation_subscription_status": invoice["status"],
                    "robot_process_automation_subscription_expires_at": expires_at,
                }
            ).eq(
                "robot_process_automation_subscription_id",
                invoice["subscription"],
            ).execute()
        else:
            get_note_subscription = (
                supabase.table("businesses")
                .select("note_taking_subscription_id")
                .eq("note_taking_subscription_id", invoice["subscription"])
                .execute()
            )
            if get_note_subscription.data:
                expires_at = datetime.fromtimestamp(
                    invoice["lines"]["data"][0]["period"]["end"]
                ).isoformat()
                supabase.table("businesses").update(
                    {
                        "note_taking_active": True,
                        "note_taking_subscription_status": invoice["status"],
                        "note_taking_subscription_expires_at": expires_at,
                    }
                ).eq("note_taking_subscription_id", invoice["subscription"]).execute()

        supabase.table("notifications").insert(
            {
                "user_id": get_user.data[0]["admin_id"],
                "message": f"Payment successful for subscription: ${amount_paid}",
                "is_read": False,
                "created_at": datetime.now().isoformat(),
                "type": "payment",
            }
        ).execute()

    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        amount_paid = invoice["amount_due"] / 100
        subscription_id = invoice["subscription"]
        customer_id = invoice["customer"]
        payment_intent = invoice.get("payment_intent")
        if payment_intent:
            pi = stripe.PaymentIntent.retrieve(payment_intent)
            if pi["status"] == "requires_payment_method":
                print(
                    f"Payment failed for subscription {subscription_id}: requires_payment_method"
                )
                get_user = (
                    supabase.table("businesses")
                    .select("admin_id")
                    .eq("customer_id", customer_id)
                    .execute()
                )
                supabase.table("billing_history").insert(
                    {
                        "user_id": get_user.data[0]["admin_id"],
                        "amount": amount_paid,
                        "invoice_id": invoice["id"],
                        "subscription_id": invoice["subscription"],
                        "invoice_url": invoice["hosted_invoice_url"],
                        "invoice_pdf_url": invoice["invoice_pdf"],
                        "status": invoice["status"],
                        "created_at": datetime.now().isoformat(),
                    }
                ).execute()

                supabase.table("notifications").insert(
                    {
                        "user_id": get_user.data[0]["admin_id"],
                        "message": f"Payment failed for subscription: Update your payment method",
                        "is_read": False,
                        "created_at": datetime.now().isoformat(),
                        "type": "payment",
                    }
                ).execute()
            else:
                print(
                    f"Payment failed for subscription {subscription_id}: {pi['status']}"
                )
                get_user = (
                    supabase.table("businesses")
                    .select("admin_id")
                    .eq("customer_id", customer_id)
                    .execute()
                )
                supabase.table("notifications").insert(
                    {
                        "user_id": get_user.data[0]["admin_id"],
                        "message": f"Payment failed for subscription: {pi['status']}",
                        "is_read": False,
                        "created_at": datetime.now().isoformat(),
                        "type": "payment",
                    }
                ).execute()
            get_rpa_subscription = (
                supabase.table("businesses")
                .select("robot_process_automation_subscription_id")
                .eq(
                    "robot_process_automation_subscription_id",
                    invoice["subscription"],
                )
                .execute()
            )
            if get_rpa_subscription.data:
                supabase.table("businesses").update(
                    {
                        "robot_process_automation_active": False,
                        "robot_process_automation_subscription_status": "inactive",
                    }
                ).eq(
                    "robot_process_automation_subscription_id",
                    invoice["subscription"],
                ).execute()
            else:
                get_note_subscription = (
                    supabase.table("businesses")
                    .select("note_taking_subscription_id")
                    .eq("note_taking_subscription_id", invoice["subscription"])
                    .execute()
                )
                if get_note_subscription.data:
                    supabase.table("businesses").update(
                        {
                            "note_taking_active": False,
                            "note_taking_subscription_status": "inactive",
                        }
                    ).eq(
                        "note_taking_subscription_id", invoice["subscription"]
                    ).execute()
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        subscription_id = subscription["id"]
        customer_id = subscription["customer"]
        status = subscription["status"]
        trial_end = subscription.get("trial_end")
        quantity = subscription["items"]["data"][0]["quantity"]

        previous_attributes = event["data"].get("previous_attributes", {})
        existing = (
            supabase.table("businesses")
            .select("*")
            .eq("customer_id", customer_id)
            .execute()
        )

        # --- CASE 1: Detect if trial just ended ---
        if (
            trial_end
            and datetime.utcnow().timestamp() > trial_end
            and status == "active"
        ):

            if existing.data:
                if (
                    existing.data[0]["note_taking_subscription_id"] == subscription_id
                    and existing.data[0]["note_taking_subscription_status"]
                    == "trialing"
                ):
                    supabase.table("businesses").update(
                        {"note_taking_subscription_status": "active"}
                    ).eq("admin_id", existing.data[0]["admin_id"]).execute()
                    supabase.table("notifications").insert(
                        {
                            "user_id": existing.data[0]["admin_id"],
                            "message": f"Stretchnote capture trial ended",
                            "is_read": False,
                            "created_at": datetime.now().isoformat(),
                            "type": "payment",
                        }
                    ).execute()
                elif (
                    existing.data[0]["robot_process_automation_subscription_id"]
                    == subscription_id
                    and existing.data[0]["robot_process_automation_subscription_status"]
                    == "trialing"
                ):
                    supabase.table("businesses").update(
                        {"robot_process_automation_subscription_status": "active"}
                    ).eq("admin_id", existing.data[0]["admin_id"]).execute()
                    supabase.table("notifications").insert(
                        {
                            "user_id": existing.data[0]["admin_id"],
                            "message": f"Stretchnote insight trial ended",
                            "is_read": False,
                            "created_at": datetime.now().isoformat(),
                            "type": "payment",
                        }
                    ).execute()

                else:
                    # already marked, skip
                    pass

        # --- CASE 2: Detect if quantity changed (flexologist added/removed) ---
        elif "items" in previous_attributes or "quantity" in str(previous_attributes):
            old_quantity = (
                previous_attributes.get("items", {})
                .get("data", [{}])[0]
                .get("quantity", None)
            )

            if old_quantity is not None and old_quantity != quantity:
                service = None

                if get_user.data[0]["note_taking_subscription_id"] == subscription_id:
                    service = "note-taking"
                else:
                    service = "robot"

                get_user = (
                    supabase.table("businesses")
                    .select("admin_id")
                    .eq("customer_id", customer_id)
                    .execute()
                )

                if get_user.data:
                    supabase.table("notifications").insert(
                        {
                            "user_id": get_user.data[0]["admin_id"],
                            "message": f'{"A new flexologist" if service == "note-taking" else "A new location"} has been added to your subscription',
                            "is_read": False,
                            "created_at": datetime.now().isoformat(),
                            "type": "payment",
                        }
                    ).execute()

    elif event["type"] == "customer.subscription.created":
        subscription = event["data"]["object"]
        subscription_id = subscription["id"]
        customer_id = subscription["customer"]
        quantity = subscription["items"]["data"][0]["quantity"]
        print(
            f"Subscription {subscription_id} created for customer {customer_id} with {quantity} flexologists"
        )
        get_user = (
            supabase.table("businesses")
            .select("*")
            .eq("customer_id", customer_id)
            .execute()
        )
        message = ""
        if get_user.data[0]["note_taking_subscription_id"] == subscription_id:
            message = "Stretchnote capture subscription created successfully"
        else:
            message = "Stretchnote insight subscription created successfully"

        if subscription["status"] == "trialing" and subscription.get("trial_end"):
            trial_end_date = datetime.fromtimestamp(subscription["trial_end"]).strftime(
                "%Y-%m-%d"
            )
            message += f" with trial ending on {trial_end_date}"
        supabase.table("notifications").insert(
            {
                "user_id": get_user.data[0]["admin_id"],
                "message": message,
                "is_read": False,
                "created_at": datetime.now().isoformat(),
                "type": "payment",
            }
        ).execute()
    elif event["type"] == "customer.subscription.trial_will_end":
        subscription = event["data"]["object"]
        subscription_id = subscription["id"]
        customer_id = subscription["customer"]
        get_user = (
            supabase.table("businesses")
            .select("*")
            .eq("customer_id", customer_id)
            .execute()
        )
        service = None

        if get_user.data[0]["note_taking_subscription_id"] == subscription_id:
            service = "note-taking"
        else:
            service = "robot"
        supabase.table("notifications").insert(
            {
                "user_id": get_user.data[0]["admin_id"],
                "message": f'{"Stretchnote Capture" if service == "note-taking" else "Stretchnote Insights"} subscription trial will end in 3 days',
                "is_read": False,
                "created_at": datetime.now().isoformat(),
                "type": "payment",
            }
        ).execute()
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        subscription_id = subscription["id"]
        customer_id = subscription["customer"]
        get_user = (
            supabase.table("businesses")
            .select("*")
            .eq("customer_id", customer_id)
            .execute()
        )
        if get_user.data[0]["note_taking_subscription_id"] == subscription_id:
            supabase.table("businesses").update(
                {
                    "note_taking_active": False,
                    "note_taking_subscription_status": "cancelled",
                }
            ).eq("admin_id", get_user.data[0]["admin_id"]).execute()
        else:
            rule_arn = update_user_rule_schedule(
                username=get_user.data[0]["username"],
                state="DISABLED",
            )
            if rule_arn:
                supabase.table("robot_process_automation_config").update(
                    {"active": False}
                ).eq("admin_id", get_user.data[0]["admin_id"]).execute()
                supabase.table("businesses").update(
                    {
                        "robot_process_automation_active": False,
                        "robot_process_automation_subscription_status": "cancelled",
                    }
                ).eq("admin_id", get_user.data[0]["admin_id"]).execute()

    return jsonify({"status": "success"}), 200


def init_payment_webhook_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/payment/webhook")
