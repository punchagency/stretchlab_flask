from flask import Blueprint, request, jsonify
import stripe
from dotenv import load_dotenv
import os
from datetime import datetime

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
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        subscription_id = subscription["id"]
        customer_id = subscription["customer"]
        quantity = subscription["items"]["data"][0]["quantity"]
        status = subscription["status"]
        previous_attributes = event["data"].get("previous_attributes", {})
        get_user = (
            supabase.table("businesses")
            .select("admin_id")
            .eq("customer_id", customer_id)
            .execute()
        )

        if (
            "status" in previous_attributes
            and previous_attributes["status"] == "trialing"
            and status == "active"
        ):
            print(f"Trial ended for subscription {subscription_id}, now active")
            supabase.table("notifications").insert(
                {
                    "user_id": get_user.data[0]["admin_id"],
                    "message": "Your trial has ended and your subscription is now active.",
                    "is_read": False,
                    "created_at": datetime.now().isoformat(),
                    "type": "payment",
                }
            ).execute()

        if "items" in previous_attributes:
            print(
                f"Subscription {subscription_id} updated: {quantity} flexologists, status: {status}"
            )
            supabase.table("notifications").insert(
                {
                    "user_id": get_user.data[0]["admin_id"],
                    "message": f"A new flexologist has been added to your subscription",
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
            .select("admin_id")
            .eq("customer_id", customer_id)
            .execute()
        )
        message = "Subscription created successfully"
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

    return jsonify({"status": "success"}), 200


def init_payment_webhook_routes(app):
    global supabase
    supabase = app.config["SUPABASE"]
    app.register_blueprint(routes, url_prefix="/api/payment/webhook")
