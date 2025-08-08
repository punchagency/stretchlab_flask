from flask_mail import Message
from flask import current_app
from threading import Thread


def send_async_email(app, msg):
    with app.app_context():
        app.extensions["mail"].send(msg)


def send_email(subject, recipients, body, html=None):

    app = current_app._get_current_object()
    msg = Message(subject=subject, recipients=recipients, body=body, html=html)

    try:
        thread = Thread(target=send_async_email, args=[app, msg])
        thread.start()
        return {"success": True, "message": "Email sent successfully!"}
    except Exception as e:
        return {"success": False, "error": f"Error sending email: {str(e)}"}
