from fastapi.testclient import TestClient

from app.admin_main import app as admin_app
from app.db import engine
from app.user_main import app as user_app


def mounted_api_paths(application):
    return {path.removeprefix("/api/v1") for path in application.openapi()["paths"] if path.startswith("/api/v1/")}


def test_user_and_admin_are_distinct_apps_over_shared_database():
    assert user_app is not admin_app
    assert user_app.state is not admin_app.state
    assert engine is not None


def test_user_api_excludes_admin_management_routes():
    paths = mounted_api_paths(user_app)
    assert "/auth/login" in paths
    assert "/chat" in paths
    assert "/admin/document-upload" not in paths
    assert "/super-admin/pending-documents" not in paths
    assert "/registrations/{registration_id}/review" not in paths


def test_admin_api_excludes_user_chat_routes():
    paths = mounted_api_paths(admin_app)
    assert "/auth/login" in paths
    assert "/admin/document-upload" in paths
    assert "/super-admin/pending-documents" in paths
    assert "/chat" not in paths
    assert "/registrations/{registration_id}/review" in paths


def test_launcher_request_log_includes_success_and_unauthorized_status(capsys):
    client = TestClient(admin_app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401

    output = capsys.readouterr().out
    assert "[ADMIN] GET /health 200 OK request_id=" in output
    assert "[ADMIN] GET /api/v1/auth/me 401 Unauthorized request_id=" in output
