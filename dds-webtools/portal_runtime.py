"""Login stateless: Firebase Hosting encaminha somente o cookie __session."""
import os
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def _serializer(purpose="login"):
    key = os.getenv("APP_SECRET_KEY")
    if not key:
        if os.getenv("K_SERVICE"):
            raise RuntimeError("APP_SECRET_KEY obrigatório")
        key = "dev-secret-key-please-change-in-production"
    return URLSafeTimedSerializer(key, salt=f"dds-{purpose}-challenge-v1")


def issue_login_challenge(purpose="login"):
    return _serializer(purpose).dumps(secrets.token_urlsafe(32))


def validate_login_challenge(token, header, purpose="login"):
    # Header customizado exige preflight em origens externas; não habilitar CORS
    # para bootstrap/login. O desafio também precisa da assinatura e validade.
    if not token or not header or not secrets.compare_digest(token, header):
        return False
    try:
        return bool(_serializer(purpose).loads(token, max_age=1800 if purpose == "access" else 600))
    except (BadSignature, SignatureExpired):
        return False
