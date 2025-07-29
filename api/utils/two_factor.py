import pyotp
import qrcode
import base64
import io
import secrets
import json
import bcrypt


def generate_totp_secret():
    return pyotp.random_base32()


def generate_qr_code(secret, email, issuer="StretchLab"):
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(totp_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_str = base64.b64encode(buffer.getvalue()).decode()

    return {
        "qr_code": f"data:image/png;base64,{img_str}",
        "secret": secret,
        "totp_uri": totp_uri,
    }


def verify_totp_code(secret, code):
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code)
    except Exception:
        return False


def generate_backup_codes(count=10):
    backup_codes = []
    for _ in range(count):
        code = secrets.token_hex(4).upper()
        backup_codes.append(code)
    return backup_codes


def hash_backup_codes(backup_codes):
    hashed_codes = []
    for code in backup_codes:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(code.encode("utf-8"), salt)
        hashed_codes.append(hashed.decode("utf-8"))
    return hashed_codes


def verify_backup_code(hashed_backup_codes, code):
    if not hashed_backup_codes:
        return False

    if isinstance(hashed_backup_codes, str):
        try:
            hashed_backup_codes = json.loads(hashed_backup_codes)
        except json.JSONDecodeError:
            return False

    code_upper = code.upper()
    for hashed_code in hashed_backup_codes:
        if bcrypt.checkpw(code_upper.encode("utf-8"), hashed_code.encode("utf-8")):
            return True
    return False


def remove_used_backup_code(hashed_backup_codes, used_code):
    if not hashed_backup_codes:
        return hashed_backup_codes

    if isinstance(hashed_backup_codes, str):
        try:
            hashed_backup_codes = json.loads(hashed_backup_codes)
        except json.JSONDecodeError:
            return hashed_backup_codes

    used_code_upper = used_code.upper()
    remaining_codes = []

    for hashed_code in hashed_backup_codes:
        if not bcrypt.checkpw(
            used_code_upper.encode("utf-8"), hashed_code.encode("utf-8")
        ):
            remaining_codes.append(hashed_code)

    return remaining_codes
