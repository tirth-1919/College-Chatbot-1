"""seed_accounts.py

Idempotent seed script to create initial user and admin accounts for the AI FAQ College Chat Bot.

Accounts created:
1. User Side:
   - Email: 1@gmail.com, Password: 1, Role: user, College: None
2. Admin Side:
   - Email: 1@gmail.com, Password: 1, Role: super_admin, College: None (All colleges)
   - Email: 2@gmail.com, Password: 2, Role: college_admin, College: AIT (col-ait-001)
   - Email: 3@gmail.com, Password: 3, Role: college_admin, College: RCTI (col-rcti-004)

Safe to run multiple times without creating duplicate records or throwing errors.
"""

import sys
from pathlib import Path

# Add project root and backend directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.app.db import SessionLocal, set_tenant_scope
from backend.app.models import User, College
from backend.app.security import hash_password
from sqlalchemy import select


COLLEGE_CONFIGS = [
    {
        "name": "Ahmedabad Institute of Technology",
        "code": "col-ait-001",
        "aliases": ["AIT", "Ahmedabad Institute of Tech"],
        "status": "approved",
    },
    {
        "name": "R.C. Technical Institute",
        "code": "col-rcti-004",
        "aliases": ["RCTI", "RC Technical Institute"],
        "status": "approved",
    },
]

USERS_CONFIG = [
    # User side
    {
        "name": "User One",
        "email": "1@gmail.com",
        "password": "1",
        "role": "user",
        "college_code": None,
    },
    {
        "name": "AIT User",
        "email": "2@gmail.com",
        "password": "2",
        "role": "user",
        "college_code": "col-ait-001",
    },
    {
        "name": "RCTI User",
        "email": "3@gmail.com",
        "password": "3",
        "role": "user",
        "college_code": "col-rcti-004",
    },
    # Admin side
    {
        "name": "Super Admin",
        "email": "1@gmail.com",
        "password": "1",
        "role": "super_admin",
        "college_code": None,
    },
    {
        "name": "AIT Admin",
        "email": "2@gmail.com",
        "password": "2",
        "role": "college_admin",
        "college_code": "col-ait-001",
    },
    {
        "name": "RCTI Admin",
        "email": "3@gmail.com",
        "password": "3",
        "role": "college_admin",
        "college_code": "col-rcti-004",
    },
]


def seed():
    with SessionLocal() as db:
        # Elevate tenant scope for bootstrapping
        set_tenant_scope(db, None, "super_admin", 0)

        # 1. Upsert colleges
        colleges_by_code = {}
        for c_data in COLLEGE_CONFIGS:
            college = db.scalar(select(College).where(College.code == c_data["code"]))
            if not college:
                college = db.scalar(select(College).where(College.name == c_data["name"]))
            if not college and c_data["code"] == "col-ait-001":
                college = db.scalar(select(College).where(College.code == "AIT"))

            if not college:
                college = College(
                    name=c_data["name"],
                    code=c_data["code"],
                    aliases=c_data["aliases"],
                    status=c_data["status"],
                )
                db.add(college)
                db.flush()
                print(f"Created college: {college.name} ({college.code})")
            else:
                college.name = c_data["name"]
                college.code = c_data["code"]
                college.aliases = c_data["aliases"]
                college.status = c_data["status"]
                db.flush()
                print(f"Updated college: {college.name} ({college.code})")

            colleges_by_code[c_data["code"]] = college

        # 2. Upsert users
        for u_data in USERS_CONFIG:
            college_id = None
            if u_data["college_code"]:
                col = colleges_by_code.get(u_data["college_code"])
                if col:
                    college_id = col.id

            user = db.scalar(
                select(User).where(
                    User.email == u_data["email"].lower(),
                    User.role == u_data["role"],
                )
            )

            pwd_hash = hash_password(u_data["password"])
            if not user:
                user = User(
                    name=u_data["name"],
                    email=u_data["email"].lower(),
                    password_hash=pwd_hash,
                    role=u_data["role"],
                    college_id=college_id,
                    email_verified=True,
                    failed_logins=0,
                    login_version=1,
                    locked_until=None,
                )
                db.add(user)
                db.flush()
                print(f"Created user: {user.email} (Role: {user.role}, College ID: {user.college_id})")
            else:
                user.name = u_data["name"]
                user.password_hash = pwd_hash
                user.college_id = college_id
                user.email_verified = True
                user.failed_logins = 0
                user.locked_until = None
                db.flush()
                print(f"Updated user: {user.email} (Role: {user.role}, College ID: {user.college_id})")

        db.commit()
        print("\n[SUCCESS] Seed accounts and colleges verified successfully.")


if __name__ == "__main__":
    seed()
