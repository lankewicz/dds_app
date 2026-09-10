import os
import sys

# Garante que o Python encontre os módulos do projeto
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base_dir)

# Define a credencial para o script rodar localmente
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'd:\programas\DDS\firebase_config.json'

from produtividade.services.cache_service import build_filters_cache

if __name__ == "__main__":
    try:
        cache = build_filters_cache()
        print("Cache construído com sucesso!")
        print(f"Regiões: {len(cache['regioes'])}")
        print(f"Cidades: {len(cache['cidades'])}")
        print(f"Equipes: {len(cache['equipes'])}")
    except Exception as e:
        print(f"Erro ao construir cache: {e}")
