import io
import unittest
import zipfile
from datetime import datetime
from unittest.mock import patch

from bdo.services.exportador_service import (
    exportar_totais_separados_por_contrato_zip,
)


class ExportScopeTests(unittest.TestCase):
    def test_gera_um_par_de_arquivos_por_contrato(self):
        def fake_export(_service, contracts, *_args, **_kwargs):
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr("Totais_Consolidados_por_Contrato.xlsx", contracts[0])
                archive.writestr(
                    "Totais_Consolidados_por_Contrato_Diferencas.xlsx", contracts[0]
                )
            return payload.getvalue()

        with patch(
            "bdo.services.exportador_service.exportar_totais_consolidados_zip",
            side_effect=fake_export,
        ):
            result = exportar_totais_separados_por_contrato_zip(
                object(), ["4600025149", "4600025150"],
                datetime(2026, 7, 1), datetime(2026, 7, 31), False,
            )

        with zipfile.ZipFile(io.BytesIO(result), "r") as archive:
            names = sorted(archive.namelist())
        self.assertEqual(len(names), 4)
        self.assertTrue(any("4600025149" in name for name in names))
        self.assertTrue(any("4600025150" in name for name in names))


if __name__ == "__main__":
    unittest.main()
