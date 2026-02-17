import time
import pyotp


def generate_totp(secret: str) -> str:
    totp = pyotp.TOTP(secret)
    return totp.now()


def get_totp_remaining_seconds() -> int:
    return 30 - int(time.time()) % 30


def validate_totp_secret(secret: str) -> bool:
    try:
        pyotp.TOTP(secret)
        return True
    except Exception:
        return False
