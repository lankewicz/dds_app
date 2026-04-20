"""
============================================================
FILE: web_app.py
FUNCTION: Flask application entrypoint for the DDS Admin Site (single service).
          Provides:
            - Status endpoint (optional)
            - Admin panel under /admin

          Cloud Run entrypoint (recommended):
            gunicorn -b :8080 web_app:app
============================================================
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any

from flask import Flask, request, jsonify, render_template

from config import Config
from admin_routes import admin_bp


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    # Register admin
    app.register_blueprint(admin_bp)

    # Simple status page (optional). Compatible with your existing web_status idea.
    _status_payload: Dict[str, Any] = {"status": "ok", "updated_at": None, "data": {}}

    @app.get("/")
    def home():
        return render_template("status.html", payload=_status_payload)

    @app.get("/health")
    def health():
        return {"status": "ok", "time": int(datetime.now(timezone.utc).timestamp())}

    @app.post("/update_status")
    def update_status():
        # Optional endpoint for external workers to post status data.
        try:
            body = request.get_json(force=True, silent=False)
        except Exception:
            body = None
        if not isinstance(body, dict):
            return jsonify({"ok": False, "error": "Invalid JSON"}), 400

        _status_payload["data"] = body
        _status_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        return jsonify({"ok": True})

    return app


app = create_app()


if __name__ == "__main__":
    # Local dev only. In Cloud Run use gunicorn.
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=True)
