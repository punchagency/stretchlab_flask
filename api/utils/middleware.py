from functools import wraps
from flask import request, jsonify


def require_bearer_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return (
                jsonify(
                    {
                        "error": "Authorization header missing or invalid",
                        "status": "error",
                    }
                ),
                401,
            )

        token = auth_header.split(" ")[1]
        if token == "":
            return (
                jsonify(
                    {
                        "error": "Authorization header missing or invalid",
                        "status": "error",
                    }
                ),
                401,
            )

        kwargs["token"] = token
        return f(*args, **kwargs)

    return decorated_function
