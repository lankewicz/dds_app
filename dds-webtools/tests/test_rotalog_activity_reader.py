import gzip
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bdo.services import rotalog_activity_reader as reader
from bdo.services.rotalog_change_tracker import _decode_json_object


def event(identity="a", **changes):
    return {"id": identity, "teamKey": "T1", "entityId": "service-1", "type": "C",
            "protocol": "20265804191700", "status": "EXECUCAO",
            "occurredAt": "2026-10-20T00:01:00-03:00", "timeSource": "consolidated", **changes}


def window(items=None, **changes):
    return {"schemaVersion": 1, "company": "ChicoEletro", "timezone": "America/Sao_Paulo",
            "windowHours": 24, "updatedAt": "2026-10-20T00:02:00-03:00",
            "items": [event()] if items is None else items, **changes}


class ActivityReaderTests(unittest.TestCase):
    def setUp(self):
        reader._cache.clear()
        self.env = patch.dict(os.environ, {"ROTALOG_EMPRESA": "ChicoEletro",
            "ROTALOG_TEAM_STORAGE_PREFIX": "custom/chico/rotalog/equipes",
            "ROTALOG_COMPANY_STORAGE_PREFIXES": '{"Outra":"custom/outra/rotalog"}'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_full_dates_offsets_teams_and_same_protocol_distinct_occurrences(self):
        payload = window([event("yesterday", occurredAt="2026-10-19T23:59:00-03:00"),
                          event("new", teamKey="T2"),
                          event("offset", occurredAt="2026-10-20T03:02:00+00:00")])
        self.assertEqual([i["id"] for i in reader.validate_window(payload, "ChicoEletro")["items"]],
                         ["offset", "new", "yesterday"])

    def test_invalid_documents_rejected_atomically(self):
        bad = [window(schemaVersion=True), window(schemaVersion=2), window(company="Outra"),
               window(items={}), window(timezone="UTC"), window(windowHours=48),
               window(updatedAt="bad"), window([event(occurredAt="2026-02-30T00:00:00-03:00")]),
               window([event(occurredAt="2026-10-20T00:00:00")]), window([event(type="X")]),
               window([event(protocol=123)]), window([event(entityId="")]), window([event(status="OTHER")])]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises((TypeError, ValueError)):
                reader.validate_window(payload, "ChicoEletro")

    def test_replacement_correction_removal_empty_and_failures(self):
        store = Mock()
        payloads = [window([event("a"), event("removed")]),
                    window([event("a", occurredAt="2026-10-20T00:05:00-03:00")]),
                    OSError("offline"), {}, window(company="Outra"), window([])]
        store.load_blob.side_effect = payloads
        with patch.object(reader, "RotalogGcsSnapshotStore", return_value=store), \
             patch("bdo.services.rotalog_reader.get_adaptive_rotalog_cache_ttl_seconds", return_value=0):
            first = reader.read_activity_window("ChicoEletro")
            corrected = reader.read_activity_window("ChicoEletro")
            self.assertEqual(len(first["items"]), 2)
            self.assertEqual(len(corrected["items"]), 1)
            self.assertEqual(corrected["items"][0]["occurredAt"], "2026-10-20T00:05:00-03:00")
            for _ in range(3):
                failed = reader.read_activity_window("ChicoEletro")
                self.assertFalse(failed["available"])
                self.assertEqual(failed["items"], corrected["items"])
            empty = reader.read_activity_window("ChicoEletro")
            self.assertTrue(empty["available"])
            self.assertEqual(empty["items"], [])
        store.save_blob.assert_not_called()

    def test_missing_first_file_is_not_valid_empty(self):
        with patch.object(reader, "RotalogGcsSnapshotStore") as factory:
            factory.return_value.load_blob.return_value = {}
            result = reader.read_activity_window("ChicoEletro")
        self.assertFalse(result["available"])
        self.assertIsNone(result["items"])

    def test_roots_cache_isolation_and_ttl_do_not_depend_on_updated_at(self):
        self.assertEqual(reader.event_blob("ChicoEletro"), "custom/chico/rotalog/events/current/index.json.gz")
        self.assertEqual(reader.event_blob("Outra"), "custom/outra/rotalog/events/current/index.json.gz")
        with self.assertRaises(ValueError):
            reader.event_blob("Desconhecida")
        store = Mock()
        store.load_blob.side_effect = [window(updatedAt="2020-01-01T00:00:00-03:00"), OSError("offline")]
        with patch.object(reader, "RotalogGcsSnapshotStore", return_value=store), \
             patch("bdo.services.rotalog_reader.get_adaptive_rotalog_cache_ttl_seconds", return_value=180):
            first = reader.read_activity_window("ChicoEletro")
            first["items"].clear()  # Callers cannot change cached data.
            self.assertEqual(len(reader.read_activity_window("ChicoEletro")["items"]), 1)
            self.assertTrue(reader.read_activity_window("ChicoEletro")["available"])
            other = reader.read_activity_window("Outra")
            self.assertFalse(other["available"])
            self.assertIsNone(other["items"])
            self.assertEqual(store.load_blob.call_count, 2)

    def test_duplicate_id_correction(self):
        result = reader.validate_window(window([event(), event(occurredAt="2026-10-20T01:00:00-03:00")]), "ChicoEletro")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["occurredAt"], "2026-10-20T01:00:00-03:00")

    def test_existing_storage_decoder_handles_utf8_gzip(self):
        payload = window([event(entityId="ocorrência")])
        compressed = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(reader.validate_window(_decode_json_object(compressed), "ChicoEletro"), payload)


if __name__ == "__main__":
    unittest.main()
