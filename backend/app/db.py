from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings
import sqlalchemy as sa

def _resolve_sqlite_url(url: str) -> str:
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        raw_path = url[len("sqlite:///"):]
        p = Path(raw_path)
        if not p.is_absolute():
            backend_dir = Path(__file__).resolve().parent.parent
            if not p.exists():
                candidate = backend_dir / p.name
                if candidate.exists():
                    return f"sqlite:///{candidate.as_posix()}"
                candidate_sub = backend_dir / p
                if candidate_sub.exists():
                    return f"sqlite:///{candidate_sub.as_posix()}"
            else:
                # If it exists in cwd but not in backend_dir, prefer backend_dir if backend/chatbot.db exists
                backend_db = backend_dir / "chatbot.db"
                if p.name == "chatbot.db" and backend_db.exists() and p.resolve() != backend_db.resolve():
                    return f"sqlite:///{backend_db.as_posix()}"
    return url

# Try PostgreSQL first, fall back to SQLite if unavailable
def create_engine_with_fallback():
    if settings.database_url.startswith("postgresql"):
        try:
            test_engine = create_engine(settings.database_url, pool_pre_ping=True)
            with test_engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            return test_engine
        except Exception:
            print("PostgreSQL unavailable, falling back to SQLite")
            fallback_url = _resolve_sqlite_url(settings.database_url_fallback)
            return create_engine(fallback_url, pool_pre_ping=True, connect_args={"check_same_thread": False})
    else:
        resolved_url = _resolve_sqlite_url(settings.database_url)
        return create_engine(resolved_url, pool_pre_ping=True, connect_args={"check_same_thread": False} if resolved_url.startswith("sqlite") else {})

engine = create_engine_with_fallback()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase): pass

@event.listens_for(SessionLocal, "after_begin")
def _apply_tenant_scope(session, transaction, connection):
    if session.info.get("tenant_role"):
        connection.exec_driver_sql("SELECT set_config('app.tenant_id', %s, true), set_config('app.user_role', %s, true), set_config('app.user_id', %s, true)" if connection.dialect.name == "postgresql" else "SELECT 1", (str(session.info.get("tenant_id") or ""), session.info["tenant_role"], str(session.info.get("user_id") or "")) if connection.dialect.name == "postgresql" else ())

def set_tenant_scope(db, college_id, role, user_id=None):
    db.info["tenant_id"] = college_id
    db.info["tenant_role"] = role
    db.info["user_id"] = user_id or db.info.get("user_id")
    if db.bind.dialect.name == "postgresql":
        db.execute(__import__("sqlalchemy").text("SELECT set_config('app.tenant_id', :cid, true), set_config('app.user_role', :role, true), set_config('app.user_id', :uid, true)"), {"cid": str(college_id or ""), "role": role, "uid": str(db.info.get("user_id") or "")})

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
