from itsdangerous import URLSafeSerializer, BadSignature
from app.supabase_client import SECRET_KEY

_COOKIE_NAME = "session"

serializer = URLSafeSerializer(SECRET_KEY, salt="class-library-session")


def set_session_cookie(response, access_token: str, refresh_token: str, user_id: str, email: str):
    payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user_id,
        "email": email,
    }
    value = serializer.dumps(payload)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=value,
        httponly=True,
        samesite="lax",
        secure=False,  # فـ localhost
        max_age=60 * 60 * 24 * 7,  # 7 days
        path="/",
    )


def clear_session_cookie(response):
    response.delete_cookie(_COOKIE_NAME, path="/")


def read_session_cookie(request):
    raw = request.cookies.get(_COOKIE_NAME)
    if not raw:
        return None
    try:
        return serializer.loads(raw)
    except BadSignature:
        return None
