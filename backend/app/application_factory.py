"""Build isolated User and Admin ASGI applications over shared services/data."""
from __future__ import annotations

import logging
import time
import uuid
import copy
from http import HTTPStatus

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import compile_path

from .config import settings

logger = logging.getLogger("chatbot.http")
AUTH_PREFIXES = ("/auth/",)
USER_PREFIXES = (
    "/conversations", "/chat", "/feedback", "/colleges", "/registrations",
    "/account", "/widget", "/audio", "/enquiries", "/privacy",
)
ADMIN_PREFIXES = ("/admin/", "/super/", "/super-admin/")


def create_application(side: str) -> FastAPI:
    if side not in {"user", "admin"}:
        raise ValueError("side must be 'user' or 'admin'")

    # Importing main registers the existing handlers and shared database models;
    # only the selected routes are exposed by this process.
    from .main import api as shared_api

    application = FastAPI(
        title=f"Multi-college FAQ {side.title()} API",
        version="1.0",
        openapi_url="/openapi.json",
    )
    origins = (
        ("http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001")
        if side == "user"
        else ("http://localhost:3001", "http://127.0.0.1:3001", "http://localhost:3000", "http://127.0.0.1:3000")
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Widget-Key"],
    )

    @application.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed id=%s method=%s path=%s", request_id, request.method, request.url.path)
            elapsed = int((time.monotonic() - started) * 1000)
            print(f"[{side.upper()}] {request.method} {request.url.path} 500 Internal Server Error request_id={request_id} duration_ms={elapsed}", flush=True)
            raise
        response.headers["X-Request-ID"] = request_id
        elapsed = int((time.monotonic() - started) * 1000)
        reason = HTTPStatus(response.status_code).phrase if response.status_code in HTTPStatus._value2member_map_ else "Unknown Status"
        print(f"[{side.upper()}] {request.method} {request.url.path} {response.status_code} {reason} request_id={request_id} duration_ms={elapsed}", flush=True)
        return response

    @application.get("/health")
    def health():
        return {"status": "ok", "application": side, "database": "shared"}

    # The original API child declares paths relative to the /api/v1 mount.
    # Copy only the selected route objects, retaining their dependencies and
    # authorization checks; no handlers or data models are duplicated.
    selected = APIRouter()
    for route in shared_api.router.routes:
        path = getattr(route, "path", "")
        # Some legacy handlers include the API prefix themselves while most
        # are mounted relative to it. Normalize both styles to one prefix.
        if path.startswith("/api/v1/"):
            route = copy.copy(route)
            route.path = path[len("/api/v1"):]
            route.path_regex, route.path_format, route.param_convertors = compile_path(route.path)
            path = route.path
        is_auth = path.startswith(AUTH_PREFIXES)
        if side == "admin":
            is_side = path.startswith(ADMIN_PREFIXES) or path in {
                "/registrations/{registration_id}/checks",
                "/registrations/{registration_id}/review",
            }
        else:
            is_side = path.startswith(USER_PREFIXES) and not path.endswith("/review")
        if is_auth or is_side:
            selected.routes.append(route)
    application.include_router(selected, prefix="/api/v1")
    return application
