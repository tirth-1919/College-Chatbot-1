"""test_auth_and_lifecycle.py

Tests for User Side and Admin Side authentication, tenant isolation, and API segregation.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app, ChatInput, RegistrationReview
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import User, College
from sqlalchemy import select
from pydantic import ValidationError


def get_client(origin="http://localhost:3000"):
    return TestClient(app, headers={"Origin": origin})


def test_chat_request_ignores_client_supplied_college():
    request = ChatInput(message="BCA fees", college=999)
    assert not hasattr(request, "college")


def test_registration_review_rejects_unknown_decisions():
    with pytest.raises(ValidationError):
        RegistrationReview(decision="appove")


def test_health_endpoints():
    c = get_client()
    r1 = c.get("/health")
    assert r1.status_code == 200
    assert r1.json()["database"] == "ok"

    r2 = c.get("/api/v1/health")
    assert r2.status_code == 200
    assert r2.json()["database"] == "ok"


def test_user_login_on_user_side():
    c = get_client("http://localhost:3000")
    settings.app_side = "user"

    # 1@gmail.com as USER
    res = c.post("/api/v1/auth/login", json={"email": "1@gmail.com", "password": "1"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["email"] == "1@gmail.com"
    assert data["role"] == "user"


def test_signup_rejects_password_shorter_than_eight_characters():
    settings.app_side = "user"
    response = get_client().post(
        "/api/v1/auth/signup",
        json={
            "name": "New User",
            "email": "short-password@example.com",
            "password": "1234567",
            "consent": True,
        },
    )
    assert response.status_code == 422


def test_admin_cannot_login_on_user_side():
    c = get_client("http://localhost:3000")
    settings.app_side = "user"

    # 2@gmail.com is AIT admin, should be rejected on User Side
    res = c.post("/api/v1/auth/login", json={"email": "2@gmail.com", "password": "2"})
    assert res.status_code == 403
    assert "User login accepts only USER accounts" in res.text

    # 3@gmail.com is RCTI admin, should be rejected on User Side
    res = c.post("/api/v1/auth/login", json={"email": "3@gmail.com", "password": "3"})
    assert res.status_code == 403


def test_super_admin_login_on_admin_side():
    c = get_client("http://localhost:3001")
    settings.app_side = "admin"

    # 1@gmail.com as SUPER_ADMIN
    res = c.post("/api/v1/auth/login", json={"email": "1@gmail.com", "password": "1"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["email"] == "1@gmail.com"
    assert data["role"] == "super_admin"

    # Super admin can access super overview
    res_overview = c.get("/api/v1/super/overview", cookies=res.cookies)
    assert res_overview.status_code == 200


def test_ait_admin_login_and_tenant_isolation():
    c = get_client("http://localhost:3001")
    settings.app_side = "admin"

    # 2@gmail.com as AIT admin
    res = c.post("/api/v1/auth/login", json={"email": "2@gmail.com", "password": "2"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["email"] == "2@gmail.com"
    assert data["role"] == "college_admin"
    assert data["college_id"] == 1  # AIT

    # AIT admin can access overview
    res_overview = c.get("/api/v1/admin/overview", cookies=res.cookies)
    assert res_overview.status_code == 200
    assert "Ahmedabad Institute of Technology" in res_overview.json().get("college", "")

    # AIT admin CANNOT access super admin overview
    res_super = c.get("/api/v1/super/overview", cookies=res.cookies)
    assert res_super.status_code == 403


def test_rcti_admin_login_and_tenant_isolation():
    c = get_client("http://localhost:3001")
    settings.app_side = "admin"

    # 3@gmail.com as RCTI admin
    res = c.post("/api/v1/auth/login", json={"email": "3@gmail.com", "password": "3"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["email"] == "3@gmail.com"
    assert data["role"] == "college_admin"
    assert data["college_id"] == 2  # RCTI

    # RCTI admin can access overview
    res_overview = c.get("/api/v1/admin/overview", cookies=res.cookies)
    assert res_overview.status_code == 200
    assert "R.C. Technical Institute" in res_overview.json().get("college", "")

    # RCTI admin CANNOT access super admin overview
    res_super = c.get("/api/v1/super/overview", cookies=res.cookies)
    assert res_super.status_code == 403


def test_user_cannot_login_on_admin_side():
    c = get_client("http://localhost:3001")
    settings.app_side = "admin"

    with SessionLocal() as db:
        only_user = db.scalar(select(User).where(User.email == "pure_user@example.com"))
        if not only_user:
            from backend.app.security import hash_password
            db.add(User(name="Pure User", email="pure_user@example.com", password_hash=hash_password("password"), role="user", email_verified=True))
            db.commit()

    res = c.post("/api/v1/auth/login", json={"email": "pure_user@example.com", "password": "password"})
    assert res.status_code == 403
    assert "Reject accounts that do not have admin permissions" in res.text


def test_admin_apis_disabled_on_user_side():
    c = get_client("http://localhost:3000")
    settings.app_side = "user"
    res = c.post("/api/v1/auth/login", json={"email": "1@gmail.com", "password": "1"})
    assert res.status_code == 200

    # Try hitting admin facts
    res_admin = c.get("/api/v1/admin/facts", cookies=res.cookies)
    assert res_admin.status_code == 403
