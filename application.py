# file used for api creation when frontend created
from api import create_app
from flask_cors import CORS

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
