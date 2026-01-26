"""
============================================================
FILE: firestore_sessions.py
FUNCTION: Optional Firestore mirror writer for DDS ONLINE sessions.
          This module is disabled by default. If ENABLE_FIRESTORE=true,
          the site will upsert a record in collection DDS_Sessions using
          sessionId as document id.
============================================================
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:  # pragma: no cover
    firebase_admin = None
    credentials = None
    firestore = None


def _ensure_app_initialized() -> None:
    if firebase_admin is None:
        raise RuntimeError("firebase-admin is not installed")

    if firebase_admin._apps:
        return

    # Cloud Run: prefer Application Default Credentials via service account.
    # If GOOGLE_APPLICATION_CREDENTIALS is set, firebase_admin will use it.
    firebase_admin.initialize_app()


def upsert_dds_session(session_payload: Dict[str, Any]) -> None:
    """Upsert a simplified session record into Firestore (DDS_Sessions)."""
    _ensure_app_initialized()

    db = firestore.client()
    session_id = session_payload.get("sessionId") or session_payload.get("channelName")
    if not session_id:
        raise ValueError("session_payload must contain sessionId")

    doc_ref = db.collection("DDS_Sessions").document(session_id)

    now = datetime.now(timezone.utc)
    body: Dict[str, Any] = {
        "type": "online",
        "status": session_payload.get("status", "scheduled"),
        "hostTeam": session_payload.get("hostTeam"),
        "subject": session_payload.get("subject"),
        "date": session_payload.get("date"),
        "time": session_payload.get("time"),
        "durationMin": session_payload.get("durationMin"),
        "timezone": session_payload.get("timezone"),
        "sessionId": session_payload.get("sessionId"),
        "channelName": session_payload.get("channelName"),
        "month_ref": session_payload.get("month_ref"),
        "scheduledStartTs": session_payload.get("scheduledStartTs"),
        "updatedAt": now,
    }

    # Only set createdAt on first insert.
    doc = doc_ref.get()
    if not doc.exists:
        body["createdAt"] = now

    doc_ref.set(body, merge=True)
