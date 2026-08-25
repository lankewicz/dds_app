import unittest

from boletim_x_ponto.services.rotalog_tempo_real_service import (
    consolidar_turno_por_contexto,
    equipe_codigo_valido,
    intervalo_ativo_por_contexto,
    parse_group_string,
    resolver_equipe_group,
)


class RotalogTurnoContextoTests(unittest.TestCase):
    def test_t_antes_da_serie_abre_turno(self):
        turno = consolidar_turno_por_contexto([{"start": 1000}], [2000, 3000])
        self.assertEqual(turno["classificacao"], "ABERTO")
        self.assertTrue(turno["aberto"])
        self.assertEqual(turno["inicio_ms"], 1000)

    def test_t_depois_da_serie_fecha_turno(self):
        turno = consolidar_turno_por_contexto(
            [{"start": 1000}, {"start": 4000}], [2000, 3000]
        )
        self.assertEqual(turno["classificacao"], "FECHADO")
        self.assertFalse(turno["aberto"])
        self.assertEqual(turno["inicio_ms"], 1000)
        self.assertEqual(turno["fim_ms"], 4000)

    def test_sem_t_nao_fecha_automaticamente(self):
        turno = consolidar_turno_por_contexto([], [2000])
        self.assertEqual(turno["classificacao"], "DESCONHECIDO")
        self.assertIsNone(turno["fim_ms"])

    def test_ultimo_t_antes_de_nova_serie_reabre(self):
        turno = consolidar_turno_por_contexto(
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

    def test_tablet_sem_relacao_continua_sem_equipe(self):
        meta = resolver_equipe_group(parse_group_string("veiculo?-MA965 JANILSON (17 min)"), {})
        self.assertEqual(meta["equipe_codigo"], "")
        self.assertEqual(meta["origem_resolucao"], "NAO_RELACIONADO")


if __name__ == "__main__":
    unittest.main()
