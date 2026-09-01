import unittest

import pandas as pd

from bdo.services.veiculos_service import (
    construir_visao_veiculo,
    listar_veiculos,
    nome_sem_matricula,
    normalizar_veiculo,
)


class VeiculosServiceTests(unittest.TestCase):
    def test_normaliza_veiculo_e_remove_matricula(self):
        self.assertEqual(normalizar_veiculo("E3188 (3)"), "E3188")
        self.assertEqual(nome_sem_matricula("380335 - João da Silva"), "João da Silva")

    def test_constroi_cruzamento_por_veiculo_dia_e_eletricista(self):
        equipes = pd.DataFrame([{
            "Data": pd.Timestamp("2026-07-01"),
            "Data Referência - Turno": "01/07/2026 | (01/07) 08:00 - (01/07) 17:00",
            "Veículo": "E3188 (2)",
            "Contrato": "4600025149",
            "Eletricista 1 (Matrícula e Nome)": "380335 - João da Silva",
            "Eletricista 2 (Matrícula e Nome)": "385970 - Maria Souza",
            "Tempo Turno": "09:00",
            "Tempo em Atividade": "08:30",
        }])
        eventos = pd.DataFrame([{
            "Data": pd.Timestamp("2026-07-01"), "Veículo": "E3188",
            "Contrato": "4600025149", "Protocolo": "123", "Evento": "456",
            "Tipo": "Serviço", "Codigo": "UC", "Imped": "1022",
            "Inicio Deslo": "01/07/2026 08:00", "Tempo Deslo": "00:30",
            "Inicio Exec": "01/07/2026 08:30", "Fim Exec": "01/07/2026 09:30",
            "Tempo Exec": "01:00",
        }])
        boletim = pd.DataFrame([{
            "DATA": pd.Timestamp("2026-07-01"), "Funcionário": "JOAO DA SILVA",
            "Contrato": "4600025149", "HORA NORMAL": 8.0, "H.N.": 0.0,
            "H.E.": 1.0, "H.E.D.": 0.0, "H.E.N.": 0.0, "H.E.N.D.": 0.0,
        }])
        ponto = pd.DataFrame([{
            "Data": pd.Timestamp("2026-07-01"), "Nome": "JOAO DA SILVA",
            "Total Normais": 7.5, "Total Noturno": 0.0, "Extra 50%D": 0.5,
            "Extra 100%D": 0.0, "Extra 50%N": 0.0, "Extra 100%N": 0.0,
            "Interjornada": 0.0,
        }])
        boletim = pd.concat([boletim, pd.DataFrame([{
            "DATA": pd.Timestamp("2026-07-01"), "Funcionário": "MARIA SOUZA",
            "Contrato": "4600025149", "HORA NORMAL": 7.0, "H.N.": 0.0,
            "H.E.": 0.5, "H.E.D.": 0.0, "H.E.N.": 0.0, "H.E.N.D.": 0.0,
        }])], ignore_index=True)
        relacao = pd.DataFrame([{
            "Nome_Boletim": "JOAO DA SILVA",
            "Nome_Ponto_Mapeado": "JOAO DA SILVA",
        }, {
            "Nome_Boletim": "MARIA SOUZA",
            "Nome_Ponto_Mapeado": "MARIA SOUZA",
        }])

        self.assertEqual(listar_veiculos(equipes, eventos, "4600025149"), ["E3188"])
        resultado = construir_visao_veiculo(
            equipes, eventos, boletim, ponto, relacao, "E3188",
            "2026-07-01", "2026-07-31", "4600025149",
        )

        self.assertEqual(len(resultado["linhas"]), 1)
        linha = resultado["linhas"][0]
        self.assertEqual(len(linha["eletricistas"]), 2)
        self.assertEqual(linha["eletricistas"][0]["nome"], "JOAO DA SILVA")
        self.assertEqual(linha["eletricistas"][1]["nome"], "MARIA SOUZA")
        self.assertEqual(linha["rotalog"], 8.5)
        self.assertEqual(linha["boletim"][0], 15.0)
        self.assertEqual(linha["ponto"][0], 7.5)
        self.assertEqual(linha["diferenca"][0], 7.5)
        self.assertEqual(linha["turno"]["inicio_exibicao"], "01/07 08:00")
        self.assertEqual(linha["turno"]["fim_exibicao"], "01/07 17:00")
        self.assertEqual(linha["turno"]["duracao"], "09:00")
        self.assertEqual(linha["quantidade_servicos"], 1)
        servico = resultado["servicos"]["2026-07-01"][0]
        self.assertEqual(servico["protocolo"], "123")
        self.assertEqual(servico["inicio_execucao_iso"], "2026-07-01T08:30:00")
        self.assertEqual(len(resultado["eventos"]), 1)
        evento = resultado["eventos"][0]
        self.assertEqual(evento["data_exibicao"], "01/07/2026")
        self.assertEqual(evento["codigo"], "UC")
        self.assertEqual(evento["impedimento"], "1022")
        self.assertEqual(evento["tempo_deslocamento"], "00:30")
        bruto = resultado["eventos_brutos"]
        self.assertIn("Protocolo", bruto["colunas"])
        self.assertIn("Codigo", bruto["colunas"])
        self.assertEqual(len(bruto["linhas"]), 1)
        self.assertEqual(bruto["linhas"][0]["Protocolo"], "123")
        self.assertEqual(bruto["linhas"][0]["Codigo"], "UC")


if __name__ == "__main__":
    unittest.main()
