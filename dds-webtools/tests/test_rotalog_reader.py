import ast
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'monitor'))
from bdo.services import rotalog_reader as reader
from bdo.services.rotalog_change_tracker import RotalogLocalCache


class RotalogReaderTests(unittest.TestCase):
    def test_index_refresh_is_read_only_and_preserves_cache_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = RotalogLocalCache(os.path.join(directory, 'cache.json'))
            store = Mock(enabled=True)
            store.load.return_value = {'equipes': {'E3389': {'version': 2}}}
            state = {'hydrated': False, 'source': 'not_loaded', 'reads': 0}
            with patch.object(reader, '_local_cache', cache), patch.object(reader, '_durable_cache_store', store), \
                 patch.object(reader, '_durable_cache_state', state), \
                 patch('bdo.services.rotalog_monitor_source.load_monitor_index', side_effect=lambda load: (load(), 'firebase')), \
                 patch('os.path.isfile', return_value=False):
                self.assertEqual(reader.get_rotalog_live_snapshots(force=True)['E3389']['version'], 2)
                store.load.side_effect = IOError('Storage unavailable')
                self.assertEqual(reader.get_rotalog_live_snapshots(force=True)['E3389']['version'], 2)
            store.save.assert_not_called()
            store.save_blob.assert_not_called()
            store.update_blob.assert_not_called()

    def test_daily_v2_remains_compatible_with_mobile_view(self):
        from bdo.routes.rotalog_routes import _mobile_team_view
        service = {'protocolo': '50961067', 'tipo': 'CHAVE', 'categoria': 'EMERGENCIA',
                   'statusAtual': 'EXECUCAO', 'inicioExecucao': '2026-10-08T08:15:00-03:00'}
        document = {'schemaVersion': 2, 'teamKey': 'E3389', 'date': '2026-10-08',
                    'updatedAt': '2026-10-08T08:20:00-03:00',
                    'jornada': {'turno': {'status': 'ABERTO'}},
                    'ordensServico': {'atual': service, 'historico': []}}
        with patch.object(reader._team_file_repository.store, 'load_blob', return_value=document):
            daily = reader.get_rotalog_team_daily('e3389', '2026-10-08')
        self.assertEqual(daily['services'], [service])
        view = _mobile_team_view(daily)
        self.assertEqual(view['turnStatus'], 'ABERTO')
        self.assertEqual(view['service']['status'], 'EXECUCAO')
        self.assertEqual(view['service']['startExecution'], service['inicioExecucao'])

    def test_production_code_has_no_collector_imports(self):
        removed = {'rotalog_sync_task', 'rotalog_crawler_service', 'rotalog_tempo_real_service', 'rotalog_daily_archive'}
        for path in ROOT.rglob('*.py'):
            if any(part in ('tests', '.venv', 'venv', '__pycache__') for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                names = ([node.module] if isinstance(node, ast.ImportFrom) else
                         [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                for name in names:
                    self.assertFalse(name and any(part in removed for part in name.split('.')), str(path))


if __name__ == '__main__':
    unittest.main()
