"""Entrypoint de execução única para Cloud Run Job / Cloud Scheduler."""

from __future__ import annotations

import json
import logging
import sys

from boletim_x_ponto.services.rotalog_sync_task import executar_sincronizacao_rotalog


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    result = executar_sincronizacao_rotalog()
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("status") in {"success", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())