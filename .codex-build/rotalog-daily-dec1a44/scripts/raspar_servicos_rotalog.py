#!/usr/bin/env python3
"""
raspar_servicos_rotalog.py
--------------------------
Script completo de raspagem automatizada do RotaLog (Copel).
Utiliza a autenticação segura, raspagem concorrente de timelines
individuais, extração de protocolos e coordenadas GPS, gerando
os arquivos JSON consolidados por equipe e exibindo relatório
detalhado na tela.

USO:
----
  # Raspagem completa de todas as equipes com exibição detalhada
  python raspar_servicos_rotalog.py

  # Definir pasta de saída personalizada
  python raspar_servicos_rotalog.py --saida ./meus_jsons

  # Filtrar uma equipe específica (ex: E3552)
  python raspar_servicos_rotalog.py --equipe E3552
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Garante compatibilidade de encoding no Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Configura caminhos para importar os módulos do DDS Webtools
ROOT_DIR = Path(__file__).resolve().parent
if (ROOT_DIR / "dds-webtools").exists():
    BASE_DIR = ROOT_DIR / "dds-webtools"
else:
    BASE_DIR = ROOT_DIR

sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "monitor"))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def extrair_servicos_equipe(equipe_data: dict[str, Any], team_key: str, day: str) -> list[dict[str, Any]]:
    """Extrai e normaliza todos os serviços (executados e em andamento) de uma equipe."""
    from bdo.services.rotalog_team_file_repository import compact_service

    servicos: list[dict[str, Any]] = []

    # 1. Serviços executados (concluídos)
    for s in equipe_data.get("ss_executadas") or []:
        cleaned = compact_service(team_key, day, s)
        if cleaned:
            servicos.append(cleaned)

    # 2. Serviço em andamento (se houver)
    ss_andamento = equipe_data.get("ss_em_andamento")
    if isinstance(ss_andamento, dict):
        cleaned = compact_service(team_key, day, ss_andamento)
        if cleaned:
            servicos.append(cleaned)
    elif isinstance(ss_andamento, list):
        for s in ss_andamento:
            cleaned = compact_service(team_key, day, s)
            if cleaned:
                servicos.append(cleaned)

    # Ordenação por início de execução / deslocamento
    def chave_ordem(item: dict[str, Any]) -> str:
        return str(item.get("inicioExecucao") or item.get("inicioDeslocamento") or "")

    servicos.sort(key=chave_ordem)
    return servicos


def main():
    parser = argparse.ArgumentParser(
        description="Raspagem e extração completa de serviços do RotaLog Copel.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--saida",
        "-o",
        default="./saida_equipes",
        help="Diretório onde os arquivos JSON por equipe serão salvos (default: ./saida_equipes)",
    )
    parser.add_argument(
        "--equipe",
        "-e",
        default=None,
        help="Filtrar uma equipe específica (ex: E3552, E3382). Se omitido, raspa todas as equipes.",
    )
    parser.add_argument(
        "--formato",
        "-f",
        choices=["lista", "completo"],
        default="lista",
        help="Formato do JSON de saída: 'lista' (lista simples de serviços) ou 'completo' (envelope diário com current).",
    )
    args = parser.parse_args()

    print("=" * 70)
    print(" [ROTALOG] INICIANDO RASPAGEM COMPLETA E DETALHADA (COPEL)")
    print("=" * 70)

    from bdo.services.rotalog_crawler_service import CrawlerRotalog
    from bdo.services.rotalog_tempo_real_service import extrair_dados_tempo_real
    from bdo.services.rotalog_team_file_repository import compact_service

    crawler = CrawlerRotalog()
    print("[*] Conectando ao portal RotaLog e capturando todas as equipes...")

    # 1. Raspagem com enriquecimento de timeline integrado
    equipes_lista = extrair_dados_tempo_real(crawler=crawler)

    if not equipes_lista:
        print("[ERRO] Nenhuma equipe encontrada ou falha de autenticação/conexão com o RotaLog.", file=sys.stderr)
        sys.exit(1)

    total_equipes = len(equipes_lista)
    print(f"[OK] Dados capturados com sucesso: {total_equipes} equipes encontradas no sistema.")

    # 2. Preparar pasta de saída
    pasta_saida = Path(args.saida).resolve()
    pasta_saida.mkdir(parents=True, exist_ok=True)

    data_hoje = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    filtro_equipe = args.equipe.upper() if args.equipe else None

    print("\n" + "=" * 70)
    print(" RELATÓRIO DETALHADO DE SERVIÇOS POR EQUIPE")
    print("=" * 70)

    total_concluidos_geral = 0
    total_agendados_geral = 0
    total_equipes_processadas = 0

    # 3. Processar cada equipe e exibir detalhes na tela
    for eq in sorted(equipes_lista, key=lambda x: (x.get("equipe_codigo") or x.get("veiculo") or "")):
        team_key = (eq.get("equipe_codigo") or eq.get("veiculo") or "").strip().upper()
        if not team_key:
            continue
        if filtro_equipe and team_key != filtro_equipe:
            continue

        ss_executadas = eq.get("ss_executadas") or []
        ss_andamento = eq.get("ss_em_andamento") or []
        if isinstance(ss_andamento, dict):
            ss_andamento = [ss_andamento]

        ss_pendentes = eq.get("ss_pendentes") or []

        qtd_concluidos = len(ss_executadas)
        qtd_agendados = len(ss_pendentes) + len(ss_andamento)

        total_concluidos_geral += qtd_concluidos
        total_agendados_geral += qtd_agendados
        total_equipes_processadas += 1

        print(f"\n{team_key}")
        print(f"{qtd_concluidos} servicos concluidos, {qtd_agendados} serviços Agendados.")

        # Listagem dos Concluídos
        if ss_executadas:
            for s in ss_executadas:
                proto = s.get("protocolo") or s.get("protocoloBruto") or s.get("ssId")
                tipo = str(s.get("tipo") or "SERVICO").strip()
                cat = str(s.get("categoria") or "").strip()
                ini = str(s.get("inicioExecucao") or s.get("inicioDeslocamento") or "").strip()[:5]
                fim = str(s.get("termino") or s.get("retorno") or s.get("fimExecucao") or "").strip()[:5]

                horario_str = f"({ini} às {fim})" if (ini and fim) else (f"(às {ini})" if ini else "")
                cat_str = f"[{cat}]" if cat else ""

                if proto:
                    print(f"  • [Concluído] Protocolo: {proto:<10} {cat_str} {tipo:<12} {horario_str}")
                else:
                    print(f"  • [Concluído] {cat_str} {tipo:<12} {horario_str} (sem protocolo na Copel)")
        else:
            print("  • Nenhum serviço concluído até o momento.")

        # Listagem do Em Andamento
        if ss_andamento:
            for s in ss_andamento:
                proto = s.get("protocolo") or s.get("protocoloBruto") or s.get("ssId")
                tipo = str(s.get("tipo") or "SERVICO").strip()
                cat = str(s.get("categoria") or "").strip()
                ini = str(s.get("inicioExecucao") or s.get("inicioDeslocamento") or s.get("inicioHora") or "").strip()[:5]
                horario_str = f"(iniciado às {ini})" if ini else ""
                cat_str = f"[{cat}]" if cat else ""

                if proto:
                    print(f"  ➜ [Em Andamento] Protocolo: {proto:<10} {cat_str} {tipo:<12} {horario_str}")
                else:
                    print(f"  ➜ [Em Andamento] {cat_str} {tipo:<12} {horario_str}")

        # Listagem dos Agendados / Pendentes
        if ss_pendentes:
            for p in ss_pendentes:
                tipo = str(p.get("tipo") or p.get("categoria") or "SERVIÇO").strip()
                seq = str(p.get("sequencia") or "").strip()
                seq_str = f"(Fila #{seq})" if seq else ""
                print(f"  ⏳ [Agendado/Fila] {tipo:<12} {seq_str}")

        # Salva o arquivo JSON da equipe
        servicos = extrair_servicos_equipe(eq, team_key, data_hoje)
        arquivo_equipe = pasta_saida / f"{team_key}.json"

        if args.formato == "completo":
            current_service = None
            if ss_andamento:
                current_service = compact_service(team_key, data_hoje, ss_andamento[0])

            status_turno = "ABERTO" if eq.get("estado_consolidado") == "ABERTO" or eq.get("turno_aberto") else "FECHADO"

            payload = {
                "schemaVersion": 1,
                "date": data_hoje,
                "current": {
                    "turnStatus": status_turno,
                    "service": current_service,
                    "version": 1,
                },
                "services": servicos,
            }
        else:
            payload = servicos

        with arquivo_equipe.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(f" RESUMO GERAL: {total_equipes_processadas} equipes | {total_concluidos_geral} concluídos | {total_agendados_geral} agendados/em andamento.")
    print(f" Arquivos JSON salvos em: {pasta_saida}")
    print("=" * 70)


if __name__ == "__main__":
    main()
