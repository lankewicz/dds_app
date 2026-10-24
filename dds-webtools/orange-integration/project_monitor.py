"""Compose existing collector files; no scraping and no Cloud Run reads."""
import argparse
import gzip
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def run(collector, root, company, bucket):
    sys.path.insert(0, str(collector))
    from google.cloud import storage
    from coletor.torre_inputs import GcsInputs, TorreInputsSync
    from coletor.torre_composer import compose_cards
    from coletor.storage_io import load_json_with_status, write_json
    from torre_contract import publish_projection, timestamp
    from data_roots import DataRoots
    from coletor.activity_feed import update_activity_feed

    root, source = DataRoots(root, os.environ['ROTALOG_FALLBACK_ROOT'],
                            os.environ['ROTALOG_SSD_MOUNT'], os.environ['ROTALOG_SSD_UUID']).select()

    now = datetime.now(ZoneInfo('America/Sao_Paulo'))
    credentials_path = str(collector / 'firebase_config.json')
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
    client = storage.Client.from_service_account_json(credentials_path)
    prefix = os.environ['MONITOR_STORAGE_PREFIX'].strip('/') + '/'
    if company.lower() not in prefix.split('/') or '..' in prefix.split('/'):
        raise ValueError('Invalid company storage root')
    # Reuse the portal's exact catalog normalization; reads Firestore, never mutates it.
    catalog_receipt = root / 'torre/catalog-export.json'
    receipt, _ = load_json_with_status(catalog_receipt, {})
    catalog_refresh = max(300, int(os.environ.get('MONITOR_CATALOG_REFRESH_SECONDS', '3600')))
    if not receipt.get('exportedAt') or (now - timestamp(receipt['exportedAt'])).total_seconds() >= catalog_refresh:
        from services.teams_service import list_teams_map
        catalog_teams = {}
        for key, team in list_teams_map().items():
            if team.get('company') and team['company'].lower() != company.lower():
                continue
            canonical = key.strip().upper()
            if canonical in catalog_teams:
                raise ValueError('Duplicate canonical team')
            aliases = {canonical, key, str(team.get('displayName') or canonical)}
            aliases.update(team.get('aliases') or [])
            catalog_teams[canonical] = {**team, 'teamKey': canonical,
                                       'aliases': sorted(value for value in aliases if isinstance(value, str) and value.strip())}
        catalog = {'schemaVersion': 1, 'company': company, 'generatedAt': now.isoformat(), 'teams': catalog_teams}
        from coletor.torre_inputs import validate_catalog
        validate_catalog(catalog, company)
        raw = json.dumps(catalog, ensure_ascii=False, default=lambda value: value.isoformat()).encode()
        client.bucket(bucket).blob(prefix + 'dds/controle/cadastro/current.json.gz').upload_from_string(
            gzip.compress(raw), content_type='application/gzip', timeout=30)
        write_json(catalog_receipt, {'exportedAt': now.isoformat()})
    sync = TorreInputsSync(root, company, GcsInputs(client, bucket))
    status = sync.sync(now=now)
    inputs = sync.snapshot(now)
    index, state = load_json_with_status(root / 'rotalog/equipes/current/index.json.gz', {})
    if state != 'ok':
        raise ValueError('Collector index unavailable')
    items, _ = compose_cards(index, inputs, company, now)
    collected = timestamp(index['lastCollectedAt'])
    age = (now - collected).total_seconds()
    sources = {**inputs['sources'], 'rotalog': {'updatedAt': collected.isoformat(),
               'stale': bool(index.get('collectionFailed')) or age < -30 or age > 1200}}
    # The activity panel exclusively reads the collector event file, never this field.
    projection = {'schemaVersion': 1, 'company': company, 'collectedAt': collected.isoformat(),
                  'composedAt': now.isoformat(), 'stale': any(s['stale'] for s in sources.values()),
                  'sources': sources, 'items': items, 'events': [], 'summary': index.get('summary', {})}
    target = root / 'torre/current.json'
    publish_projection(target, projection, company)
    payload = gzip.compress(json.dumps(projection, ensure_ascii=False, separators=(',', ':')).encode())
    client.bucket(bucket).blob(prefix + 'torre/current.json.gz').upload_from_string(payload, content_type='application/gzip', timeout=30)
    # Fresh reconstruction from complete consolidated diaries makes removals effective.
    with tempfile.TemporaryDirectory() as temporary:
        temporary_feed = Path(temporary) / 'index.json.gz'
        for day in (now.date() - timedelta(days=1), now.date()):
            daily, daily_state = load_json_with_status(root / 'rotalog/equipes/consolidated' / (day.isoformat() + '.json'), {})
            if daily_state != 'ok' or daily.get('company') != company or not isinstance(daily.get('equipes'), dict):
                raise ValueError('Consolidated diary unavailable')
            feed = update_activity_feed(temporary_feed, company, daily['equipes'], now)['payload']
        feed_target = root / 'rotalog/events/current/index.json.gz'
        old, old_state = load_json_with_status(feed_target, {})
        if old_state == 'ok' and old.get('items') == feed['items']:
            feed['updatedAt'] = old['updatedAt']
        write_json(feed_target, feed)
        event_bytes = gzip.compress(json.dumps(feed, ensure_ascii=False, separators=(',', ':')).encode())
        client.bucket(bucket).blob(prefix + 'rotalog/events/current/index.json.gz').upload_from_string(event_bytes, content_type='application/gzip', timeout=30)
    print(json.dumps({'company': company, 'cards': len(items), 'stale': projection['stale'],
                      'inputsAvailable': status.get('available'), 'inputsError': status.get('errorType')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--collector', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--company', required=True)
    parser.add_argument('--bucket', required=True)
    args = parser.parse_args()
    run(args.collector, args.root, args.company, args.bucket)
