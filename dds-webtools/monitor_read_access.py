"""Private, short-lived Storage URLs for direct browser failover."""
import os
from datetime import timedelta


def backup_urls(company):
    import google.auth
    from google.auth.transport.requests import Request
    from google.cloud import storage
    credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    credentials.refresh(Request())
    signer = os.environ['SIGNING_SERVICE_ACCOUNT']
    bucket = storage.Client(project=project, credentials=credentials).bucket(os.environ['DDS_BUCKET_NAME'])
    prefix = os.environ.get('MONITOR_STORAGE_PREFIX', 'dados/{empresa}').replace('{empresa}', company.lower()).strip('/')
    if company.lower() not in prefix.split('/') or '..' in prefix.split('/'):
        raise ValueError('Company storage root required')
    return {name: bucket.blob(prefix + '/' + path).generate_signed_url(
        version='v4', expiration=timedelta(minutes=10), method='GET',
        service_account_email=signer, access_token=credentials.token)
        for name, path in {'monitor': 'torre/current.json.gz', 'events': 'rotalog/events/current/index.json.gz'}.items()}
