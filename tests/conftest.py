"""Shared test setup.

Puts the repository root on ``sys.path`` and redirects the app's user-data
directory into a temporary folder so tests never touch the real profile.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("KWS_DATA_DIR", tempfile.mkdtemp(prefix="kws-tests-"))

import pytest  # noqa: E402


@pytest.fixture()
def client():
    """A Flask test client with the auth + CSRF cookies already set."""
    import server.app as app_module
    import server.config as config

    token, csrf = "test-token", "test-csrf"
    application = app_module.create_app(config.load(), token, csrf)
    application.config.update(TESTING=True)
    test_client = application.test_client()
    test_client.set_cookie("kws_auth", token)
    test_client.set_cookie("kws_csrf", csrf)
    return test_client
