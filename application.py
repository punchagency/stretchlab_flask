# file used for api creation when frontend created
import sentry_sdk
from api import create_app
from flask_cors import CORS

sentry_sdk.init(
    dsn="https://5905df66c87ebb135572143fda3d8844@o4510317670891520.ingest.us.sentry.io/4510317684588544",
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
)

application = create_app()

CORS(
    application,
    resources={
        r"/*": {
            "origins": [
                "https://www.stretchnote.com",
                "https://admin.stretchnote.com",
                "http://localhost:5173",
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Client-Timezone"],
        }
    },
    supports_credentials=True,
)


if __name__ == "__main__":
    application.run(host="0.0.0.0", port=5000, debug=True)
