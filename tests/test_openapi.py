import json

from server.export_openapi import OPENAPI_FILE
from server.main import app


def test_openapi_file_is_up_to_date():
    saved = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    assert saved == app.openapi(), "openapi.json устарел — запустите: python -m server.export_openapi"


def test_openapi_describes_all_endpoints():
    paths = set(app.openapi()["paths"])
    assert {"/api/health", "/api/pick", "/api/me", "/api/invites", "/api/invites/{invite_id}", "/api/stats"} <= paths
