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
            "bucket",
            client_factory=lambda: FakeClient(uploads),
            crawler_factory=FakeCrawler,
        )
        result = archive.collect(datetime.date(2026, 9, 8))

        self.assertEqual(1, result["teams"])
        self.assertEqual(1, result["events"])
        self.assertEqual({
            "_cache/rotalog/coletas/2026-09-08/equipes.json.gz",
            "_cache/rotalog/coletas/2026-09-08/eventos.json.gz",
        }, set(uploads))
        self.assertEqual("application/json", uploads[result["teamsPath"]]["contentType"])
        self.assertEqual("gzip", uploads[result["eventsPath"]]["contentEncoding"])
        self.assertEqual("E1", uploads[result["teamsPath"]]["payload"]["records"][0]["Equipe"])
        self.assertIsNone(uploads[result["eventsPath"]]["payload"]["records"][0]["Vazio"])


if __name__ == "__main__":
    unittest.main()
