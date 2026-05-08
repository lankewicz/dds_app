import os
import sys
from pathlib import Path

# Adiciona o diretório raiz ao sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.report_service import ReportService
from app.core.logging import get_logger

logger = get_logger(__name__)

def run_fix():
    print("🚀 Iniciando Rebuild para corrigir arredondamentos...")
    ReportService.rebuild_all_caches()
    print("✅ Rebuild concluído! Os valores de Glosa e Reprovação foram arredondados no Firestore.")

if __name__ == "__main__":
    run_fix()
