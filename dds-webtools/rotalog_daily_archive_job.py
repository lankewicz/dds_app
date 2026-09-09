"""Entrypoint do Cloud Run Job para arquivar o dia anterior do ROTALOG."""

from __future__ import annotations

import json
import logging
import sys

from bdo.services.rotalog_daily_archive import DailyRotalogArchive


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    result = DailyRotalogArchive().collect()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
