import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'monitor'))


class HostingBuildTests(unittest.TestCase):
    def test_generated_pages_are_static_and_keep_api_fallback(self):
        public = ROOT.parent / 'public'
        config = json.loads((ROOT.parent / 'firebase.json').read_text(encoding='utf-8'))['hosting']
        mappings = config['rewrites']
        self.assertEqual(mappings[-1]['run']['serviceId'], 'dds-admin-site')
        self.assertTrue(all(not item['source'].startswith('/api/') for item in mappings[:-1]))
        for item in mappings[:-1]:
            text = (public / item['destination'].lstrip('/')).read_text(encoding='utf-8')
            self.assertNotIn('{{', text)
            self.assertNotIn('{%', text)
            self.assertNotIn('valdinei@', text)
            self.assertNotIn('valdinei.pco@', text)
        home = (public / 'portal/home.html').read_text(encoding='utf-8')
        self.assertIn('data-permission="admin" hidden', home)
        access = (public / 'portal/access-control.html').read_text(encoding='utf-8')
        self.assertIn('let csrfToken="";let currentIsRoot=false;', access)
        login = (public / 'portal/login.html').read_text(encoding='utf-8')
        self.assertIn('X-Portal-CSRF', login)
        self.assertIn('/api/auth/bootstrap', login)

    def test_challenges_are_signed_and_cannot_cross_purposes(self):
        from portal_runtime import issue_login_challenge, validate_login_challenge
        with patch.dict('os.environ', {'APP_SECRET_KEY': 'hosting-test-secret'}):
            login = issue_login_challenge()
            access = issue_login_challenge('access')
            self.assertTrue(validate_login_challenge(login, login))
            self.assertTrue(validate_login_challenge(access, access, 'access'))
            self.assertFalse(validate_login_challenge(login, login, 'access'))
            self.assertFalse(validate_login_challenge(login, 'different'))
            self.assertFalse(validate_login_challenge(login + 'bad', login + 'bad'))


class HostingApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        from fastapi.testclient import TestClient
        cls.main = main
        cls.client = TestClient(main.app)

    def test_anonymous_private_apis_return_401(self):
        for path in ['/api/portal/session', '/api/access-control/users', '/api/turnos', '/api/torre/access']:
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_profile_does_not_expose_secrets_and_respects_permissions(self):
        user = {'email': 'reader@example.com', 'role': 'user', 'is_root': False,
                'permissions': {'monitor'}, 'write_permissions': set()}
        with patch.object(self.main, 'authenticate_portal_request', return_value=user):
            response = self.client.get('/api/portal/session')
            denied = self.client.get('/api/access-control/users')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['permissions'], ['monitor'])
        self.assertNotIn('token', response.text.lower())
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(denied.status_code, 403)

    def test_login_and_registration_reject_missing_challenges(self):
        for path, payload in [('/api/login', {'id_token': 'invalid', 'csrf_token': ''}),
                              ('/api/request-access', {'name': 'Example User', 'email': 'reader@example.com', 'password': 'test-password'})]:
            response = self.client.post(path, json=payload)
            self.assertEqual(response.status_code, 403)

    def test_orange_access_requires_monitor_permission_and_configuration(self):
        user = {'email': 'reader@example.com', 'role': 'user', 'is_root': False,
                'permissions': set(), 'write_permissions': set()}
        settings = {'TORRE_PUBLIC_URL': 'https://orange.example.ts.net',
                    'TORRE_SIGNING_KEY': 'test-key-' * 5, 'DDS_EMPRESA_PADRAO': 'ChicoEletro'}
        with patch.object(self.main, 'authenticate_portal_request', return_value=user), patch.dict('os.environ', settings):
            self.assertEqual(self.client.get('/api/torre/access').status_code, 403)
            user['permissions'] = {'monitor'}
            response = self.client.get('/api/torre/access')
            self.assertEqual(response.status_code, 200)
            from torre_access import validate_token
            claims = validate_token(response.json()['token'], settings['TORRE_SIGNING_KEY'], 'ChicoEletro')
            self.assertEqual(claims['sub'], user['email'])
            self.assertEqual(response.headers['cache-control'], 'no-store')
            with patch.dict('os.environ', {'TORRE_PUBLIC_URL': 'http://invalid'}):
                self.assertEqual(self.client.get('/api/torre/access').status_code, 503)


if __name__ == '__main__':
    unittest.main()
