import unittest

import pandas as pd

from boletim_x_ponto.services.pacote_veiculo_service import filtrar_rotalog_veiculo


class PacoteVeiculoTests(unittest.TestCase):
    def test_filtra_variacoes_do_mesmo_veiculo_e_contrato(self):
        source = pd.DataFrame([
            {"Veículo": "E3188 (2)", "Contrato": "10", "Evento": "A"},
            {"Veículo": "E3188 (3)", "Contrato": "10", "Evento": "B"},
            {"Veículo": "E3188", "Contrato": "20", "Evento": "C"},
            {"Veículo": "E4000", "Contrato": "10", "Evento": "D"},
        ])
        result = filtrar_rotalog_veiculo(source, "E3188", "10")
        self.assertEqual(result["Evento"].tolist(), ["A", "B"])


if __name__ == "__main__":
    unittest.main()
