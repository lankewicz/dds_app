import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import portal_auth


class FakeDocument:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def get(self):
        return self

    def to_dict(self):
        return self._data


class FakeCollection:
    def __init__(self, users):
        self.users = users

    def document(self, email):
        return FakeDocument(self.users.get(email))


class FakeDb:
    def __init__(self, users):
        self.users = users

    def collection(self, name):
        assert name == "dds_users"
        return FakeCollection(self.users)


class PortalAuthTests(unittest.TestCase):
    def test_active_user_is_authorized(self):
        db = FakeDb({"user@empresa.com": {"active": True, "role": "admin"}})
        user = portal_auth.authorize_portal_user(
            {"uid": "uid-1", "email": "User@Empresa.com"}, db
        )
        self.assertEqual("user@empresa.com", user["email"])
        self.assertEqual("admin", user["role"])

    def test_admin_has_every_permission(self):
        user = {"role": "admin", "permissions": []}
        for permission in portal_auth.PORTAL_AREAS:
            self.assertTrue(portal_auth.has_permission(user, permission))

    def test_user_only_has_explicit_permissions(self):
        user = {"role": "user", "permissions": ["monitor"]}
        self.assertTrue(portal_auth.has_permission(user, "monitor"))
        self.assertFalse(portal_auth.has_permission(user, "vexpenses"))

    def test_read_permission_does_not_grant_write(self):
        user = {
            "role": "user",
            "permissions": ["monitor", "produtividade"],
            "write_permissions": [],
        }
        self.assertTrue(portal_auth.has_permission(user, "monitor"))
        self.assertFalse(portal_auth.has_write_permission(user, "monitor"))

    def test_write_permission_is_scoped_by_module(self):
        user = {
            "role": "user",
            "permissions": ["monitor", "produtividade"],
            "write_permissions": ["monitor"],
        }
        self.assertTrue(portal_auth.has_write_permission(user, "monitor"))
        self.assertFalse(portal_auth.has_write_permission(user, "produtividade"))

    def test_admin_area_requires_admin_role_even_if_in_permissions(self):
        user = {"role": "user", "permissions": ["admin"]}
        self.assertFalse(portal_auth.has_permission(user, "admin"))

    def test_root_has_full_access_without_firestore_activation(self):
        user = portal_auth.authorize_portal_user(
            {"uid": "root-1", "email": "valdinei.pco@gmail.com"}, FakeDb({})
        )
        self.assertTrue(user["is_root"])
        self.assertEqual("root", user["role"])
        self.assertTrue(portal_auth.has_permission(user, "admin"))

    def test_only_configured_emails_are_root(self):
        self.assertTrue(portal_auth.is_root_email("VALDINEI@chicoeletro.com.br"))
        self.assertFalse(portal_auth.is_root_email("outro@chicoeletro.com.br"))

    def test_path_is_mapped_to_area(self):
        self.assertEqual(
            "controle_projetos",
            portal_auth.required_permission_for_path("/controle-projetos/api/projetos"),
        )
        self.assertEqual("monitor", portal_auth.required_permission_for_path("/api/turnos"))
        self.assertIsNone(portal_auth.required_permission_for_path("/"))

    def test_inactive_user_is_rejected(self):
        db = FakeDb({"user@empresa.com": {"active": False}})
        with self.assertRaises(portal_auth.UnauthorizedUserError):
            portal_auth.authorize_portal_user({"email": "user@empresa.com"}, db)

    def test_unknown_user_is_rejected(self):
        with self.assertRaises(portal_auth.UnauthorizedUserError):
            portal_auth.authorize_portal_user(
                {"email": "unknown@empresa.com"}, FakeDb({})
            )

    @patch("portal_auth.firebase_auth.verify_session_cookie")
    @patch("portal_auth.ensure_firebase_app")
    def test_forged_cookie_is_rejected(self, _ensure_app, verify_cookie):
        verify_cookie.side_effect = ValueError("bad signature")
        with self.assertRaises(portal_auth.InvalidSessionError):
            portal_auth.verify_session_cookie("user@empresa.com")


if __name__ == "__main__":
    unittest.main()
