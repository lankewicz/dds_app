import unittest
from datetime import datetime, timedelta, timezone

from bdo.services.rotalog_tempo_real_service import (
    _parse_rotalog_popups,
    consolidar_equipes_duplicadas,
    consolidar_turno_por_contexto,
    equipe_codigo_valido,
    formatar_protocolo_copel,
    intervalo_ativo_por_contexto,
    parse_group_string,
    resolver_equipe_group,
    _obter_inicio_dia_operacional_ms,
)


class RotalogTurnoContextoTests(unittest.TestCase):
    def test_dia_operacional_vira_a_meia_noite_de_brasilia(self):
        instant = datetime.fromisoformat("2026-09-10T01:00:00+00:00")
        expected = datetime.fromisoformat("2026-09-09T00:00:00-03:00")
        self.assertEqual(_obter_inicio_dia_operacional_ms(instant), int(expected.timestamp() * 1000))

    def _turno(self, markers, services, *, hours_later=0):
        # 09h em Brasilia; desloca os antigos valores sinteticos para uma data real.
        base = datetime(2026, 9, 10, 9, tzinfo=timezone(timedelta(hours=-3)))
        offset = int(base.timestamp() * 1000)
        result = consolidar_turno_por_contexto(
            [{**m, "start": offset + m["start"]} for m in markers],
            [offset + value for value in services],
            now=base + timedelta(hours=hours_later, minutes=1),
        )
        for field in ("inicio_ms", "fim_ms"):
            if result.get(field) is not None:
                result[field] -= offset
        return result

    def test_formata_protocolo_com_prefixo_e_sufixo_rotalog(self):
        self.assertEqual(
            formatar_protocolo_copel("01.20265507121122.1.1"),
            "20265507121122",
        )
    def test_consolida_duas_linhas_da_mesma_equipe_e_agrupa_servicos(self):
        base = {
            "equipe_codigo": "E3389",
            "veiculo": "",
            "identificador_equipamento": "",
            "origem_resolucao": "PREFIXO_EQUIPE",
            "status_conexao": "online",
            "is_online": True,
            "turno_marcadores_t": [],
            "eventos_servico_ms": [],
            "intervalo": {"em_intervalo": False, "inicio_ms": None, "fim_ms": None},
            "atividade_atual": None,
            "bdo_list": [],
            "ss_executadas": [],
            "ss_pendentes": [],
        }
        primeira = {
            **base,
            "group_raw": "E3389- JOCEMAR RONALDO (online)",
            "colaborador": "JOCEMAR RONALDO",
            "ss_em_andamento": [{"status": "EXECUCAO", "tipo": "UC", "inicioIso": "2026-08-26T13:00:00+00:00"}],
        }
        segunda = {
            **base,
            "group_raw": "veiculo_-CA389 RONALDO JOCEMAR (online)",
            "colaborador": "RONALDO JOCEMAR",
            "ss_em_andamento": [{"status": "EXECUCAO", "tipo": "195", "inicioIso": "2026-08-26T14:00:00+00:00"}],
        }
        resultado = consolidar_equipes_duplicadas([primeira, segunda])
        self.assertEqual(len(resultado), 1)
        self.assertEqual({item["tipo"] for item in resultado[0]["ss_em_andamento"]}, {"UC", "195"})
        self.assertIn("JOCEMAR RONALDO", resultado[0]["group_raw"])
        self.assertIn("RONALDO JOCEMAR", resultado[0]["group_raw"])

    def test_popup_leaflet_salva_geolocalizacao_do_servico(self):
        html = r'''
        var marker = L.marker([-25.4284, -49.2733]).addTo(map).bindPopup(
          "Sequência: 9\nStatus: DESLOCANDO\nEquipe: E2269-\nProtocolo: 20265453323251.2.2\nCategoria: COMERCIAL\nTipo: 9925"
        );
        '''
        info = _parse_rotalog_popups(html)["E2269_9925"]
        self.assertEqual(info["protocolo"], "20265453323251")
        self.assertEqual(info["latitude"], -25.4284)
        self.assertEqual(info["longitude"], -49.2733)
        self.assertEqual(info["geolocalizacao"], {"latitude": -25.4284, "longitude": -49.2733})
    def test_t_antes_da_serie_abre_turno(self):
        turno = self._turno([{"start": 1000}], [2000, 3000])
        self.assertEqual(turno["classificacao"], "ABERTO")
        self.assertTrue(turno["aberto"])
        self.assertEqual(turno["inicio_ms"], 1000)

    def test_t_depois_da_serie_fecha_turno(self):
        turno = self._turno(
            [{"start": 1000}, {"start": 4000}], [2000, 3000], hours_later=3
        )
        self.assertEqual(turno["classificacao"], "FECHADO")
        self.assertFalse(turno["aberto"])
        self.assertEqual(turno["inicio_ms"], 1000)
        self.assertEqual(turno["fim_ms"], 4000)

    def test_sem_t_assume_fim_no_ultimo_servico(self):
        # Durante o dia (< 20:00), equipe sem T explícito aguardando novos despachos permanece ABERTA
        turno = self._turno([], [2000, 3000])
        self.assertEqual(turno["classificacao"], "ABERTO")
        self.assertTrue(turno["aberto"])
        self.assertEqual(turno["inicio_ms"], 2000)

    def test_ultimo_t_antes_de_nova_serie_reabre(self):
        turno = self._turno(
            [{"start": 1000}, {"start": 4000}, {"start": 5000}],
            [2000, 3000, 6000],
        )
        self.assertEqual(turno["classificacao"], "ABERTO")
        self.assertEqual(turno["inicio_ms"], 5000)

    def test_deslocamento_posterior_encerra_intervalo(self):
        intervalo = {"em_intervalo": True, "inicio_ms": 3000, "fim_ms": None}
        self.assertFalse(intervalo_ativo_por_contexto(intervalo, [2000, 4000]))

    def test_intervalo_posterior_ao_ultimo_servico_permanece(self):
        intervalo = {"em_intervalo": True, "inicio_ms": 3000, "fim_ms": None}
        self.assertTrue(intervalo_ativo_por_contexto(intervalo, [2000]))

    def test_aceita_codigos_reais_de_equipe(self):
        self.assertTrue(equipe_codigo_valido("E2148"))
        self.assertTrue(equipe_codigo_valido("E3C03"))

    def test_rejeita_placeholder_de_veiculo(self):
        self.assertFalse(equipe_codigo_valido("veiculo?"))
        self.assertFalse(equipe_codigo_valido("VEICULO_"))

    def test_resolve_prefixo_real_depois_de_veiculo(self):
        meta = resolver_equipe_group(parse_group_string("veiculo?-E3G64 AMAURI (online)"))
        self.assertEqual(meta["equipe_codigo"], "E3G64")
        self.assertEqual(meta["origem_resolucao"], "VEICULO_COM_PREFIXO_EQUIPE")

    def test_resolve_tablet_importado_depois_de_veiculo(self):
        meta = resolver_equipe_group(
            parse_group_string("veiculo?-CA226 ANTONIO IAGO (29 min)"),
            {"CA226": "E3X93"},
        )
        self.assertEqual(meta["equipe_codigo"], "E3X93")
        self.assertEqual(meta["origem_resolucao"], "IDENTIFICACAO_TABLET")

    def test_resolve_por_integrantes_quando_tablet_nao_cadastrado(self):
        lookup = {
            "MEMBER_NAME:WELLINGTON JAIR SEFERINO BENTO": "E3P14",
            "MEMBER_NAME:WILLIAN FERNANDO FERREIRA": "E3P14",
        }
        meta = resolver_equipe_group(
            parse_group_string("veiculo?-MA974 WELLINGTON WILLIAN (35 min)"),
            lookup,
        )
        self.assertEqual(meta["equipe_codigo"], "E3P14")
    def test_resolve_tablet_transitorio_mudanca_regional(self):
        lookup = {
            "CA085": "E3F43",
            "NUMERIC_TABLET:085": "E3F43",
        }
        # Equipe de Cascavel (CA085) mudando temporariamente para Maringá (MA085)
        meta = resolver_equipe_group(
            parse_group_string("veiculo?-MA085 CHRISTOPHER CLEVERSON (online)"),
            lookup,
        )
        self.assertEqual(meta["equipe_codigo"], "E3F43")
        self.assertEqual(meta["origem_resolucao"], "TABLET_NUMERICO_TRANSITORIO")

    def test_resolve_por_integrantes_ordem_invertida_dos_nomes(self):
        lookup = {
            "MEMBER_NAME:ROBERTO CARLOS SILVA": "E3B99",
            "MEMBER_NAME:CARLOS EDUARDO ALMEIDA": "E3B99",
        }
        # Ordem invertida no Rotalog: "CARLOS ROBERTO"
        meta = resolver_equipe_group(
            parse_group_string("veiculo?-LO888 CARLOS ROBERTO (10 min)"),
            lookup,
        )
        self.assertEqual(meta["equipe_codigo"], "E3B99")
        self.assertEqual(meta["origem_resolucao"], "INTEGRANTES_EQUIPE")

    def test_parse_rotalog_popup_balao_e3x12(self):
        html = """
        <div class="leaflet-popup-content">
            Sequência: 10<br/>
            Status: EXECUTANDO<br/>
            Equipe: E3X12-<br/>
            Protocolo: 50954702<br/>
            Categoria: EMERGÊNCIA<br/>
            Tipo: UC<br/>
            Início Deslocamento: 09:50<br/>
            Início Execução: 09:13<br/>
            Término: -<br/>
            Retorno: -
        </div>
        """
        popups = _parse_rotalog_popups(html)
        self.assertIn("E3X12", popups)
        info = popups["E3X12"]
        self.assertEqual(info["protocolo"], "50954702")
        self.assertEqual(info["categoria"], "EMERGÊNCIA")
        self.assertEqual(info["tipo"], "UC")
        self.assertEqual(info["inicioDeslocamento"], "09:50")
        self.assertEqual(info["inicioExecucao"], "09:13")

    def test_parse_rotalog_popup_com_html_escapado(self):
        html = r'''marker.bindPopup("Sequência: 6\nStatus: EXECUTANDO\nEquipe: veiculo?-CA228\nProtocolo: 20265445297154.1.1\nCategoria: COMERCIAL\nTipo: 192\nInício Execução: 14:04")'''
        popups = _parse_rotalog_popups(html)
        info = popups["IDENTIFIER:CA228_192"]
        self.assertEqual(info["protocolo"], "20265445297154")
        self.assertEqual(info["tipo"], "192")
    def test_parse_rotalog_popup_e2269_prioriza_equipe_e_tipo(self):
        html = """
        <div class="leaflet-popup-content">
            Sequência: 9<br/>
            Status: DESLOCANDO<br/>
            Equipe: E2269-<br/>
            Protocolo: 20265453323251.2.2<br/>
            Categoria: COMERCIAL<br/>
            Tipo: 9925<br/>
            Início Deslocamento: 15:37<br/>
            Início Execução: -<br/>
            Término: -<br/>
            Retorno: -
        </div>
        """
        popups = _parse_rotalog_popups(html)
        self.assertIn("E2269_9925", popups)
        info = popups["E2269_9925"]
        self.assertEqual(info["equipe"], "E2269")
        self.assertEqual(info["protocolo"], "20265453323251")
        self.assertEqual(info["protocoloBruto"], "20265453323251.2.2")
        self.assertEqual(info["sequencia"], "9")
        self.assertEqual(info["status"], "DESLOCANDO")
        self.assertEqual(info["inicioDeslocamento"], "15:37")
    def test_parse_rotalog_popup_por_identificador_ca228_com_protocolo_comercial(self):
        html = """
        <div class="leaflet-popup-content">
            Sequência: 6<br/>
            Status: EXECUTANDO<br/>
            Equipe: veiculo?-CA228<br/>
            Protocolo: 20265445297154.1.1<br/>
            Categoria: COMERCIAL<br/>
            Tipo: 192<br/>
            Início Deslocamento: 13:34<br/>
            Início Execução: 14:04<br/>
            Término: -<br/>
            Retorno: -
        </div>
        """
        popups = _parse_rotalog_popups(html)
        self.assertIn("IDENTIFIER:CA228", popups)
        self.assertIn("IDENTIFIER:CA228_192", popups)
        info = popups["IDENTIFIER:CA228_192"]
        self.assertEqual(info["identificadorEquipamento"], "CA228")
        self.assertEqual(info["protocolo"], "20265445297154")
        self.assertEqual(info["protocoloBruto"], "20265445297154.1.1")
        self.assertEqual(info["categoria"], "COMERCIAL")
        self.assertEqual(info["tipo"], "192")

if __name__ == "__main__":
    unittest.main()
