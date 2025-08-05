import stripe
import os
from dotenv import load_dotenv
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def create_customer(email, username):
    try:
        customer = stripe.Customer.create(name=username, email=email)
        return customer
    except Exception as e:
        print(e)
        return e


def create_setup_intent(customer_id):
    try:
        setup_intent = stripe.SetupIntent.create(
            customer=customer_id,
            automatic_payment_methods={"enabled": True},
        )
        print(setup_intent, "setup_intent")
        return setup_intent
    except Exception as e:
        print(e)
        return e


def create_payment_method(customer_id, payment_method_id):
    try:
        stripe.PaymentMethod.attach(payment_method_id, customer=customer_id)

        customer = stripe.Customer.modify(
            customer_id, invoice_settings={"default_payment_method": payment_method_id}
        )
        return {
            "status": True,
            "message": "Payment method updated successfully",
            "customer": customer,
        }
    except Exception as e:
        print(e)
        return {"status": False, "message": "Payment method update failed", "error": e}


def modify_customer_email(customer_id, email):
    try:
        customer = stripe.Customer.modify(customer_id, email=email)
        return customer
    except Exception as e:
        print(e)
        return e


def create_subscription(customer_id, price_id, quantity=1):
    try:
        trial_end_dt = datetime.now() + relativedelta(days=3)
        trial_end = int(trial_end_dt.timestamp())
        end_of_month = (
            trial_end_dt.replace(day=1) + relativedelta(months=1, days=-1)
        ).replace(hour=23, minute=59, second=59)
        billing_cycle_anchor = int(end_of_month.timestamp())
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id, "quantity": quantity}],
            payment_behavior="allow_incomplete",
            trial_end=trial_end,
            billing_cycle_anchor=billing_cycle_anchor,
            proration_behavior="create_prorations",
            expand=["latest_invoice.payment_intent"],
        )
        logging.info(subscription, "subscription")
        return {
            "subscription_id": subscription.id,
            "status": subscription.status,
        }
    except Exception as e:
        print(e, "error in create_subscription")
        return e


def restart_subscription(subscription_id):
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        # print(subscription, "subscription")
        if subscription.status == "active" and subscription.cancel_at_period_end:
            # Resume by unsetting cancel_at_period_end
            updated_sub = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=False,
                proration_behavior="create_prorations",
            )
            logging.info(f"Subscription {subscription_id} resumed.")
            return {
                "status": True,
                "subscription_id": updated_sub["id"],
                "subscription_status": updated_sub["status"],
            }
        elif subscription.status == "canceled":
            # Create a new subscription with similar details
            print(subscription, "subscription")
            customer_id = subscription["customer"]
            items = [
                {"price": item["price"]["id"], "quantity": item["quantity"]}
                for item in subscription["items"]["data"]
            ]
            print(items, "items")
            new_sub = stripe.Subscription.create(
                customer=customer_id,
                items=items,
                proration_behavior="create_prorations",
                # Optionally add billing_cycle_anchor or other params if needed
            )
            logging.info(
                f"New subscription {new_sub['id']} created to restart canceled {subscription_id}."
            )
            return {
                "status": True,
                "subscription_id": new_sub["id"],
                "subscription_status": new_sub["status"],
            }
        else:
            raise ValueError(
                f"Subscription {subscription_id} cannot be restarted (status: {subscription.status})."
            )
    except Exception as e:
        print(e)
        return e


def update_subscription(subscription_id):
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        current_quantity = subscription["items"]["data"][0]["quantity"]
        new_quantity = current_quantity + 1

        subscription = stripe.Subscription.modify(
            subscription_id,
            items=[
                {"id": subscription["items"]["data"][0]["id"], "quantity": new_quantity}
            ],
        )
        return subscription
    except Exception as e:
        print(e)
        return e


def get_subscription_details(subscription_id):
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        return subscription
    except Exception as e:
        print(e)
        return e


def cancel_subscription(subscription_id):
    try:
        subscription = stripe.Subscription.cancel(
            subscription_id, invoice_now=True, prorate=True
        )
        return subscription
    except Exception as e:
        print(e)
        return e


def retrieve_payment_method(payment_method_id):
    try:
        payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
        return payment_method
    except Exception as e:
        print(e)
        return e


def get_balance_for_month():
    try:
        first_day_this_month = datetime.now().replace(day=1)
        last_day_this_month = (
            first_day_this_month + relativedelta(months=1, days=-1)
        ).replace(hour=23, minute=59, second=59)

        balance = stripe.Balance.retrieve()

        balance_transactions = stripe.BalanceTransaction.list(
            limit=100,
            created={
                "gte": int(first_day_this_month.timestamp()),
                "lte": int(last_day_this_month.timestamp()),
            },
        )

        got_balance = (
            balance["available"][0]["amount"] / 100 if balance["available"] else 0
        )

        got_transactions = round(
            sum(
                transaction["amount"] / 100
                for transaction in balance_transactions["data"]
                if transaction["type"] == "charge"
            ),
            2,
        )

        return {
            "total_available_balance": got_balance,
            "month_transactions": got_transactions,
            "status": "success",
        }
    except Exception as e:
        print(e)
        return e


def get_invoice_details(invoice_id):
    try:
        invoice = stripe.Invoice.retrieve(invoice_id)
        return invoice
    except Exception as e:
        print(e)
        return e
