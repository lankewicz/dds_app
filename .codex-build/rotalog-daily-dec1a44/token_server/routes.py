import os
import time
import logging
from enum import Enum

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

# IMPORTA O CÓDIGO OFICIAL DA AGORA
from .agora_src.RtcTokenBuilder2 import (
    RtcTokenBuilder,
    Role_Publisher,
    Role_Subscriber,
)
from .agora_src.RtmTokenBuilder import RtmTokenBuilder, Role_Rtm_User

logger = logging.getLogger("dds-token-server")

router = APIRouter(tags=["token"])

# ==========================================================
# Configurações de ambiente
# ==========================================================

def get_app_id():
    return os.getenv("AGORA_APP_ID")

def get_app_certificate():
    return os.getenv("AGORA_APP_CERTIFICATE")

def get_api_key():
    return (os.getenv("TOKEN_SERVER_API_KEY") or "").strip() or None

# ==========================================================
# Modelos de entrada/saída
# ==========================================================

class ClientRole(str, Enum):
    host = "host"
    cohost = "cohost"
    participant = "participant"


class TokenRequest(BaseModel):
    channel: str = Field(..., min_length=1, description="Nome do canal (string)")
    uid: int = Field(..., ge=0, description="UID inteiro único no canal")
    role: ClientRole = Field(..., description="host | cohost | participant")
    expire_seconds: int = Field(
        3600,
        ge=60,
        le=24 * 60 * 60,
        description="Tempo de expiração em segundos (min 60, máx 86400)"
    )
    user_account: str | None = Field(
        None,
        min_length=1,
        description="(Opcional) Identidade RTM (string). Se omitido, usa uid como string."
    )
    api_key: str | None = Field(
        None,
        description="API key opcional; se configurada no servidor, deve bater com TOKEN_SERVER_API_KEY"
    )

class TokenResponse(BaseModel):
    token: str
    expire_at: int
    now: int
    channel: str
    uid: int
    role: ClientRole

class RtmTokenResponse(BaseModel):
    token: str
    expire_at: int
    now: int
    uid: int    

class CombinedTokenResponse(BaseModel):
    rtc_token: str
    rtm_token: str
    expire_at: int
    now: int
    channel: str
    uid: int
    role: ClientRole
    user_account: str

# ==========================================================
# Funções auxiliares
# ==========================================================

def build_rtm_token_compat(app_id: str, app_cert: str, user_account: str, expire_ts: int):
    if hasattr(RtmTokenBuilder, "build_token"):
        return RtmTokenBuilder.build_token(app_id, app_cert, user_account, Role_Rtm_User, expire_ts)
    if hasattr(RtmTokenBuilder, "buildToken"):
        return RtmTokenBuilder.buildToken(app_id, app_cert, user_account, Role_Rtm_User, expire_ts)
    if hasattr(RtmTokenBuilder, "buildTokenWithUserAccount"):
        return RtmTokenBuilder.buildTokenWithUserAccount(app_id, app_cert, user_account, Role_Rtm_User, expire_ts)
    raise RuntimeError("RtmTokenBuilder não possui métodos conhecidos.")

def map_role(client_role: ClientRole):
    if client_role in (ClientRole.host, ClientRole.cohost):
        return Role_Publisher
    return Role_Subscriber

def validate_api_key(api_key: str | None):
    expected_api_key = get_api_key()
    if not expected_api_key:
        return
    recv = (api_key or "")
    if recv != expected_api_key:
        logger.warning(f"Invalid API key: recv_len={len(recv)} exp_len={len(expected_api_key)}")
        raise HTTPException(status_code=401, detail="Invalid API key")

# ==========================================================
# Endpoints
# ==========================================================

@router.get("/health_token")
def health_token():
    app_id = (get_app_id() or "").strip()
    return {
        "status": "ok",
        "app_id_prefix": app_id[:8] if app_id else "",
        "time": int(time.time())
    }

@router.post("/token", response_model=CombinedTokenResponse)
def generate_tokens(
    payload: TokenRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    validate_api_key(payload.api_key or x_api_key)

    app_id = get_app_id()
    app_cert = get_app_certificate()
    if not app_id or not app_cert:
        raise HTTPException(status_code=500, detail="AGORA_APP_ID/CERTIFICATE not configured.")

    channel = payload.channel.strip()
    if not channel:
        raise HTTPException(status_code=400, detail="Channel name cannot be empty.")

    uid = payload.uid
    agora_role = map_role(payload.role)
    now_ts = int(time.time())
    expire_ts = now_ts + int(payload.expire_seconds)
    user_account = (payload.user_account or str(uid)).strip()

    try:
        rtc_token = RtcTokenBuilder.build_token_with_uid(
            app_id, app_cert, channel, uid, agora_role,
            token_expire=expire_ts, privilege_expire=expire_ts,
        )
        if not rtc_token or len(rtc_token) < 50:
            raise ValueError("RTC token inválido.")
            
        rtm_token = build_rtm_token_compat(app_id, app_cert, user_account, expire_ts)
        if not rtm_token or len(rtm_token) < 50:
            raise ValueError("RTM token inválido.")
            
    except Exception as e:
        logger.error(f"Erro ao gerar tokens: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate tokens: {e}")

    return CombinedTokenResponse(
        rtc_token=rtc_token,
        rtm_token=rtm_token,
        expire_at=expire_ts,
        now=now_ts,
        channel=channel,
        uid=uid,
        role=payload.role,
        user_account=user_account,
    )

@router.post("/rtc/token", response_model=TokenResponse)
def generate_rtc_token(
    payload: TokenRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    validate_api_key(payload.api_key or x_api_key)

    app_id = get_app_id()
    app_cert = get_app_certificate()
    if not app_id or not app_cert:
        raise HTTPException(status_code=500, detail="AGORA_APP_ID/CERTIFICATE not configured.")

    channel = payload.channel.strip()
    if not channel:
        raise HTTPException(status_code=400, detail="Channel name cannot be empty.")

    uid = payload.uid
    agora_role = map_role(payload.role)
    now_ts = int(time.time())
    expire_ts = now_ts + int(payload.expire_seconds)

    try:
        token = RtcTokenBuilder.build_token_with_uid(
            app_id, app_cert, channel, uid, agora_role,
            token_expire=expire_ts, privilege_expire=expire_ts,
        )
    except Exception as e:
        logger.error(f"Erro ao gerar RTC token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {e}")

    return TokenResponse(
        token=token,
        expire_at=expire_ts,
        now=now_ts,
        channel=channel,
        uid=uid,
        role=payload.role,
    )

@router.post("/rtm/token", response_model=RtmTokenResponse)
def generate_rtm_token(
    payload: TokenRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    validate_api_key(payload.api_key or x_api_key)

    app_id = get_app_id()
    app_cert = get_app_certificate()
    if not app_id or not app_cert:
        raise HTTPException(status_code=500, detail="AGORA_APP_ID/CERTIFICATE not configured.")

    now_ts = int(time.time())
    expire_ts = now_ts + int(payload.expire_seconds)
    user_account = (payload.user_account or str(payload.uid)).strip()

    try:
        rtm_token = build_rtm_token_compat(app_id, app_cert, user_account, expire_ts)
    except Exception as e:
        logger.error(f"Erro ao gerar RTM token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate RTM token: {e}")

    return RtmTokenResponse(
        token=rtm_token,
        expire_at=expire_ts,
        now=now_ts,
        uid=int(payload.uid),
    )
