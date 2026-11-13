from datetime import datetime, timedelta, timezone
import base64, hashlib, hmac, json, secrets, time
from app.core.config import settings

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt_hex, digest_hex = encoded.split("$")
        if scheme != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False

def create_access_token(subject: str, role: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": subject, "role": role, "exp": int(time.time()) + settings.access_token_expire_minutes * 60}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}"
    signature = _b64(hmac.new(settings.secret_key.encode(), signing_input.encode(), hashlib.sha256).digest())
    return f"{signing_input}.{signature}"

def decode_access_token(token: str) -> dict | None:
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}"
        expected = _b64(hmac.new(settings.secret_key.encode(), signing_input.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): return None
        if json.loads(_unb64(header)).get("alg") != "HS256": return None
        data = json.loads(_unb64(payload))
        if int(data.get("exp", 0)) <= int(time.time()): return None
        return data
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
