import datetime
import gzip
import json
import unittest

import pandas as pd

from bdo.services.rotalog_daily_archive import DailyRotalogArchive, dataframe_records


class FakeBlob:
    def __init__(self, path, uploads):
        self.path = path
        self.uploads = uploads
        self.content_encoding = None

    def upload_from_string(self, value, content_type=None):
        self.uploads[self.path] = {
            "payload": json.loads(gzip.decompress(value)),
            "contentType": content_type,
            "contentEncoding": self.content_encoding,
        }

    def download_as_bytes(self, raw_download=False):
        payload = self.uploads[self.path]["payload"]
        return gzip.compress(json.dumps(payload).encode("utf-8"))


class FakeBucket:
    def __init__(self, uploads):
        self.uploads = uploads

    def blob(self, path):
        return FakeBlob(path, self.uploads)


class FakeClient:
    def __init__(self, uploads):
        self.uploads = uploads

    def bucket(self, name):
        return FakeBucket(self.uploads)


class FakeCrawler:
    def _raspar_bloco(self, start, end):
        assert start == end == "08/09/2026"
        return (
            pd.DataFrame([{"Equipe": "E1", "Data": pd.Timestamp("2026-09-08")}]),
            pd.DataFrame([{"Protocolo": "1234567", "Vazio": float("nan")}]),
        )


class DailyArchiveTests(unittest.TestCase):
    def test_converte_datas_e_nan_para_json(self):
        records = dataframe_records(pd.DataFrame([{
            "Data": pd.Timestamp("2026-09-08"),
            "Vazio": float("nan"),
        }]))
        self.assertEqual("2026-09-08T00:00:00", records[0]["Data"])
        self.assertIsNone(records[0]["Vazio"])

    def test_salva_dois_jsons_com_caminhos_diarios(self):
        uploads = {}
        archive = DailyRotalogArchive(
            "ChicoEletro",
            "bucket",
            client_factory=lambda: FakeClient(uploads),
            crawler_factory=FakeCrawler,
        )
        result = archive.collect(
            datetime.date(2026, 9, 8),
            now=datetime.datetime(2026, 9, 9, 4, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=-3))),
        )

        self.assertEqual(1, result["teams"])
        self.assertEqual(1, result["events"])
        self.assertEqual({
            "dados/chicoeletro/rotalog/diario/2026-09-08/equipes.json.gz",
            "dados/chicoeletro/rotalog/diario/2026-09-08/eventos.json.gz",
        }, set(uploads))
        self.assertEqual("application/json", uploads[result["teamsPath"]]["contentType"])
        self.assertEqual("gzip", uploads[result["eventsPath"]]["contentEncoding"])
        self.assertEqual("E1", uploads[result["teamsPath"]]["payload"]["records"][0]["Equipe"])
        self.assertIsNone(uploads[result["eventsPath"]]["payload"]["records"][0]["Vazio"])
        self.assertEqual("ChicoEletro", uploads[result["teamsPath"]]["payload"]["company"])
        self.assertEqual("chicoeletro", archive.load("2026-09-08", "equipes")["companyKey"])

    def test_grava_somente_no_novo_repositorio(self):
        uploads = {}
        archive = DailyRotalogArchive(
            "ChicoEletro",
            "bucket",
            client_factory=lambda: FakeClient(uploads),
            crawler_factory=FakeCrawler,
        )
        result = archive.collect(
            datetime.date(2026, 9, 8),
            now=datetime.datetime(2026, 10, 1, 4, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=-3))),
        )
        self.assertEqual({
            "dados/chicoeletro/rotalog/diario/2026-09-08/equipes.json.gz",
            "dados/chicoeletro/rotalog/diario/2026-09-08/eventos.json.gz",
        }, set(uploads))

    def test_empresa_e_tipo_sao_obrigatorios(self):
        with self.assertRaises(RuntimeError):
            DailyRotalogArchive("", "bucket")
        archive = DailyRotalogArchive("Chico Elétrico", "bucket")
        self.assertEqual("dados/chico-eletrico/rotalog/diario/2026-09-08/eventos.json.gz",
                         archive.path("2026-09-08", "eventos"))
        with self.assertRaises(ValueError):
            archive.path("2026-09-08", "outro")


if __name__ == "__main__":
    unittest.main()
