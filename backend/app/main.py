from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, quote
import secrets, re, smtplib
import io, hashlib, csv, json, time, os
import zipfile
import logging
import sys
import socket, struct
import math
import uuid
from email.message import EmailMessage
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Response, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from .db import Base, engine, get_db, SessionLocal, set_tenant_scope
from .models import *
from .security import hash_password, verify_password, issue_token, issue_refresh_token, token_hash, current_user, require, tenant, auth_cookie_name, role_allowed_for_side
from .config import settings
from .privacy import mask_personal_data
from .matching import fuzzy_college_resolution

# DO NOT call create_all() here - use Alembic migrations instead
app=FastAPI(title="Multi-college FAQ API",version="1.0",openapi_url="/api/v1/openapi.json")
logger=logging.getLogger(__name__)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","Accept","X-Widget-Key"])
api=FastAPI()
_rate_fallback={}
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    REQUESTS=Counter("chatbot_api_requests_total","API requests",["method","route","status"])
    LATENCY=Histogram("chatbot_api_request_seconds","API request latency",["route"])
    CRAWL_FAILURES=Gauge("chatbot_crawl_failures_last_hour","Crawl jobs that failed in the last hour")
    REDIS_AVAILABLE=Gauge("chatbot_redis_available","Whether Redis answered the last metrics probe")
except ImportError:
    REQUESTS=LATENCY=CRAWL_FAILURES=REDIS_AVAILABLE=None

@app.middleware("http")
async def headers(request,call_next):
    request_id=request.headers.get("X-Request-ID") or str(uuid.uuid4()); started=time.monotonic()
    path=request.url.path; limits={"/api/v1/auth/login":8,"/api/v1/auth/verify-mfa":8,"/api/v1/auth/signup":8,"/api/v1/chat":40,"/api/v1/widget/chat":60}
    if request.method in {"POST","PUT","PATCH","DELETE"} and path!="/api/v1/widget/chat":
        raw_origin=request.headers.get("Origin")
        origin=(raw_origin or "").rstrip("/")
        allowed={value.strip().rstrip("/") for value in settings.cors_origins.split(",") if value.strip()}
        allowed.add(settings.public_base_url.rstrip("/"))
        has_session_cookie=any(request.cookies.get(name) for name in ("access_token","refresh_token","user_access_token","user_refresh_token","admin_access_token","admin_refresh_token"))
        if (raw_origin and origin not in allowed) or (has_session_cookie and not raw_origin):
            if not has_session_cookie or raw_origin not in allowed:
                return JSONResponse(status_code=403,content={"detail":"CORS origin not allowed"})
    response=await call_next(request)
    response.headers["X-Request-ID"]=request_id
    duration=time.monotonic()-started
    if REQUESTS and LATENCY: REQUESTS.labels(method=request.method,route=path,status=response.status_code).inc(); LATENCY.labels(route=path).observe(duration)
    if path in limits and duration>limits[path]: _rate_fallback[path]=_rate_fallback.get(path,0)+1
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request:Request,exc:Exception):
    import traceback; tb=traceback.format_exc()
    import logging; logging.error(f"Unhandled exception: {tb}")
    return JSONResponse(status_code=500,content={"detail":"Internal server error","request_id":request.headers.get("X-Request-ID")})

@app.get("/health")
def health_check():
    return {"status":"ok","maintenance_mode":settings.maintenance_mode}

@app.get("/metrics")
def metrics():
    if REQUESTS: return Response(content=generate_latest(),media_type=CONTENT_TYPE_LATEST)
    return Response(status_code=503)

app.mount("/api/v1",api)

class SignupRequest(BaseModel):
    name: str = Field(..., max_length=160)
    email: EmailStr
    password: str = Field(..., min_length=8)
    consent: str = ""

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class VerifyMFARequest(BaseModel):
    email: EmailStr
    code: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

class ToggleMFARequest(BaseModel):
    password: str
    enabled: bool = False

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    password: str = Field(..., min_length=8)

class UpdateConversationRequest(BaseModel):
    title: str = Field(..., max_length=200)
    pinned: bool = False

class ReviewRegistrationRequest(BaseModel):
    decision: str
    reason: str = ""

class RejectDocumentRequest(BaseModel):
    reason: str = ""

class UpdateProfileRequest(BaseModel):
    name: str = Field(..., max_length=160)

class DeleteAccountRequest(BaseModel):
    password: str

class ChatAttachmentRequest(BaseModel):
    question: str = ""
    language: str = "en-IN"
    conversation_id: int | None = None

@api.post("/auth/signup")
async def signup(req: SignupRequest, db: Session = Depends(get_db)):
    if req.consent != "on":
        raise HTTPException(400, "Consent required")
    if db.scalar(select(User).where(User.email == req.email)):
        raise HTTPException(409, "Email already registered")
    hashed = hash_password(req.password)
    u = User(name=req.name[:160], email=req.email.lower(), password_hash=hashed, role="user", mfa_enabled=False)
    db.add(u); db.commit(); db.refresh(u)
    code = secrets.token_urlsafe(16)[:6].upper()
    from .security import verify_token
    token = verify_token({"sub": str(u.id), "email": u.email, "role": u.role, "college_id": u.college_id}, sign=True)
    from .models import EmailVerification
    ev = EmailVerification(user_id=u.id, code=code, expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    db.add(ev); db.commit()
    return {"user_id": u.id, "email": u.email, "development_code": code, "message": "Verification code sent (development mode)"}

@api.post("/auth/verify-email")
async def verify_email(req: VerifyEmailRequest, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == req.email.lower()))
    if not u:
        raise HTTPException(404, "User not found")
    ev = db.scalar(select(EmailVerification).where(EmailVerification.user_id == u.id, EmailVerification.code == req.code, EmailVerification.expires_at > datetime.now(timezone.utc)))
    if not ev:
        raise HTTPException(400, "Invalid or expired code")
    db.delete(ev); u.email_verified = True; db.commit()
    return {"message": "Email verified"}

def auth_user_query(email: str):
    clean_email = email.strip().lower()
    query = select(User).where(func.lower(User.email) == clean_email)
    if settings.app_side == "user":
        return query.where(User.role=="user")
    if settings.app_side == "admin":
        return query.where(User.role.in_(("super_admin","college_admin","editor","viewer")))
    return query

def set_portal_auth_cookies(response:JSONResponse,access_token:str,refresh_token:str):
    response.set_cookie(key=auth_cookie_name("access"),value=access_token,httponly=True,secure=settings.cookie_secure,samesite="lax",max_age=settings.access_token_minutes*60,domain=None)
    response.set_cookie(key=auth_cookie_name("refresh"),value=refresh_token,httponly=True,secure=settings.cookie_secure,samesite="lax",max_age=30*24*60*60,domain=None)
    if settings.app_side in {"user","admin"}:
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")

@api.post("/auth/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    email_clean = str(req.email).strip().lower()
    pwd_str = str(req.password)
    pwd_clean = pwd_str.strip()

    u = db.scalar(auth_user_query(email_clean))
    if not u:
        any_user = db.scalar(select(User).where(func.lower(User.email) == email_clean))
        if any_user:
            if settings.app_side == "user" and any_user.role in ("super_admin", "college_admin", "editor", "viewer"):
                raise HTTPException(401, f"This account is registered as an Administrator ({any_user.role.replace('_', ' ').title()}). Please sign in on the Admin Portal (http://localhost:3001).")
            elif settings.app_side == "admin" and any_user.role == "user":
                raise HTTPException(401, "This account is registered as a student/user. Please sign in on the User Portal (http://localhost:3000).")
        raise HTTPException(401, "Invalid credentials")

    # Verify password (allowing both exact password and trimmed password)
    is_valid = verify_password(pwd_str, u.password_hash) or (bool(pwd_clean) and verify_password(pwd_clean, u.password_hash))
    if not is_valid:
        raise HTTPException(401, "Invalid credentials")
    if u.force_password_change:
        raise HTTPException(403, "Password change required")
    if u.mfa_enabled:
        code = secrets.token_urlsafe(16)[:6].upper()
        from .models import EmailVerification
        existing = db.scalar(select(EmailVerification).where(EmailVerification.user_id == u.id, EmailVerification.expires_at > datetime.now(timezone.utc)))
        if existing:
            db.delete(existing)
        ev = EmailVerification(user_id=u.id, code=code, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
        db.add(ev)
        db.commit()
        return {"mfa_required": True, "email": u.email, "development_code": code}

    access_token = issue_token(u)
    refresh_token = issue_refresh_token(u)
    response = JSONResponse({"id": u.id, "name": u.name, "email": u.email, "role": u.role, "college_id": u.college_id})
    set_portal_auth_cookies(response, access_token, refresh_token)
    return response

@api.post("/auth/verify-mfa")
async def verify_mfa(req: VerifyMFARequest, db: Session = Depends(get_db)):
    u = db.scalar(auth_user_query(req.email.strip().lower()))
    if not u:
        raise HTTPException(404, "User not found")
    ev = db.scalar(select(EmailVerification).where(EmailVerification.user_id == u.id, EmailVerification.code == req.code, EmailVerification.expires_at > datetime.now(timezone.utc)))
    if not ev:
        raise HTTPException(400, "Invalid or expired code")
    db.delete(ev)
    access_token = issue_token(u)
    refresh_token = issue_refresh_token(u)
    response = JSONResponse({"id": u.id, "name": u.name, "email": u.email, "role": u.role, "college_id": u.college_id})
    set_portal_auth_cookies(response, access_token, refresh_token)
    return response

@api.post("/auth/refresh")
def refresh_token_endpoint(request:Request,db:Session=Depends(get_db)):
    refresh_token=request.cookies.get(auth_cookie_name("refresh"))
    if not refresh_token: raise HTTPException(401,"No refresh token")
    from .security import verify_token
    payload=verify_token(refresh_token,verify=True)
    u=db.get(User,int(payload["sub"]))
    if not u: raise HTTPException(401,"User not found")
    if not role_allowed_for_side(u.role): raise HTTPException(403,"Account cannot sign in to this portal")
    access_token=issue_token(u)
    response=JSONResponse({"id":u.id,"name":u.name,"email":u.email,"role":u.role,"college_id":u.college_id})
    set_portal_auth_cookies(response,access_token,refresh_token)
    return response

@api.post("/auth/logout")
def logout(request:Request):
    response=JSONResponse({"message":"Logged out"})
    response.delete_cookie(auth_cookie_name("access"))
    response.delete_cookie(auth_cookie_name("refresh"))
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response

@api.get("/auth/me")
def get_current_user_endpoint(u:User=Depends(current_user),db:Session=Depends(get_db)):
    return {"id":u.id,"name":u.name,"email":u.email,"role":u.role,"college_id":u.college_id,"mfa_enabled":u.mfa_enabled,"force_password_change":u.force_password_change}

@api.post("/auth/change-password")
async def change_password(req: ChangePasswordRequest, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(req.current_password, u.password_hash):
        raise HTTPException(401, "Current password incorrect")
    u.password_hash = hash_password(req.new_password); u.force_password_change = False; db.commit()
    return {"message": "Password changed"}

@api.patch("/auth/mfa")
async def toggle_mfa(req: ToggleMFARequest, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(req.password, u.password_hash):
        raise HTTPException(401, "Password incorrect")
    u.mfa_enabled = req.enabled; db.commit()
    return {"message": "MFA updated", "enabled": req.enabled}

@api.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == req.email.lower()))
    if not u:
        return {"message": "If the account exists, a reset code has been sent"}
    code = secrets.token_urlsafe(16)[:6].upper()
    from .models import EmailVerification
    existing = db.scalar(select(EmailVerification).where(EmailVerification.user_id == u.id, EmailVerification.expires_at > datetime.now(timezone.utc)))
    if existing:
        db.delete(existing)
    ev = EmailVerification(user_id=u.id, code=code, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db.add(ev); db.commit()
    return {"message": "If the account exists, a reset code has been sent", "development_code": code}

@api.post("/auth/reset-password")
async def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == req.email.lower()))
    if not u:
        raise HTTPException(404, "User not found")
    ev = db.scalar(select(EmailVerification).where(EmailVerification.user_id == u.id, EmailVerification.code == req.code, EmailVerification.expires_at > datetime.now(timezone.utc)))
    if not ev:
        raise HTTPException(400, "Invalid or expired code")
    db.delete(ev); u.password_hash = hash_password(req.password); u.force_password_change = False; db.commit()
    return {"message": "Password reset successful"}

@api.get("/auth/sessions")
def list_sessions(u:User=Depends(current_user),db:Session=Depends(get_db)):
    sessions=list(db.scalars(select(SessionToken).where(SessionToken.user_id==u.id,SessionToken.expires_at>datetime.now(timezone.utc))))
    return [{"id":s.id,"device":s.device or "Unknown","expires_at":s.expires_at.isoformat(),"active":s.expires_at>datetime.now(timezone.utc)} for s in sessions]

@api.delete("/auth/sessions/{session_id}")
def revoke_session(session_id:int,u:User=Depends(current_user),db:Session=Depends(get_db)):
    s=db.get(SessionToken,session_id)
    if not s or s.user_id!=u.id: raise HTTPException(404,"Session not found")
    db.delete(s); db.commit()
    return {"revoked":True}

@api.post("/conversations")
def create_conversation(u:User=Depends(current_user),db:Session=Depends(get_db)):
    conv=Conversation(user_id=u.id,college_id=u.college_id,title="New chat")
    db.add(conv); db.commit(); db.refresh(conv)
    return {"id":conv.id,"title":conv.title}

@api.get("/conversations")
def list_conversations(u:User=Depends(current_user),db:Session=Depends(get_db)):
    convs=list(db.scalars(select(Conversation).where(Conversation.user_id==u.id).order_by(Conversation.updated_at.desc()).limit(100)))
    return [{"id":c.id,"title":c.title,"college_id":c.college_id,"updated_at":c.updated_at.isoformat() if c.updated_at else None} for c in convs]

@api.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id:int,u:User=Depends(current_user),db:Session=Depends(get_db)):
    conv=db.get(Conversation,conversation_id)
    if not conv or conv.user_id!=u.id: raise HTTPException(404,"Conversation not found")
    msgs=list(db.scalars(select(Message).where(Message.conversation_id==conversation_id).order_by(Message.created_at)))
    return [{"id":m.id,"role":m.role,"content":m.content,"source_badge":m.source_badge,"sources":m.sources,"contact":m.contact,"location":m.location} for m in msgs]

@api.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id:int,u:User=Depends(current_user),db:Session=Depends(get_db)):
    conv=db.get(Conversation,conversation_id)
    if not conv or conv.user_id!=u.id: raise HTTPException(404,"Conversation not found")
    db.query(Message).filter(Message.conversation_id==conversation_id).delete(synchronize_session=False)
    db.delete(conv); db.commit()
    return {"deleted":True}

@api.patch("/conversations/{conversation_id}")
def update_conversation(conversation_id: int, req: UpdateConversationRequest, u: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != u.id:
        raise HTTPException(404, "Conversation not found")
    conv.title = req.title[:200]; conv.pinned = req.pinned; conv.updated_at = datetime.now(timezone.utc); db.commit()
    return {"id": conv.id, "title": conv.title, "pinned": conv.pinned}

@api.post("/chat")
async def chat_endpoint(request:Request, body:dict, db:Session=Depends(get_db), u:User=Depends(current_user)):
    conversation_id=body.get("conversation_id")
    message=body.get("message","")[:2000]
    requested_college_id=body.get("college_id")
    language=body.get("language","en-IN")
    if not message: raise HTTPException(400,"Message required")
    if conversation_id:
        conv=db.get(Conversation,conversation_id)
        if not conv or conv.user_id!=u.id: raise HTTPException(404,"Conversation not found")
        college_id=conv.college_id or requested_college_id or u.college_id
    else:
        college_id=requested_college_id or u.college_id

    if college_id:
        college_record=db.get(College,int(college_id))
        if not college_record or college_record.status!="approved":
            raise HTTPException(404,"College not found")
    else:
        approved_colleges=list(db.scalars(select(College).where(College.status=="approved")))
        college_record,_=fuzzy_college_resolution(message,approved_colleges)
        if college_record:
            college_id=college_record.id

    if not conversation_id:
        conv=Conversation(user_id=u.id,college_id=college_id,title=message[:100])
        db.add(conv); db.flush()
    elif college_id and not conv.college_id:
        conv.college_id=college_id

    user_msg=Message(conversation_id=conv.id,role="user",content=message)
    db.add(user_msg); db.flush()
    set_tenant_scope(db,conv.college_id,u.role,u.id)
    question=mask_personal_data(message)
    normalized_question=" ".join(re.findall(r"[a-z0-9]+",question.casefold()))
    college_aliases=[college_record.name,college_record.code,*(college_record.aliases or [])] if college_id and college_record else []
    is_college_selection=any(
        normalized_question==" ".join(re.findall(r"[a-z0-9]+",alias.casefold()))
        for alias in college_aliases if alias
    )
    words=[w.lower() for w in re.findall(r"\b\w+\b",question)]
    facts=list(db.scalars(select(Fact).outerjoin(Page,Fact.source_page_id==Page.id).where(Fact.college_id==conv.college_id,Fact.confidence>0,or_(Fact.source_page_id.is_(None),Page.admin_verified==True)).limit(300)))
    ranked=sorted([(sum(w in f"{f.title} {f.category} {f.value}".lower() for w in words),f) for f in facts],key=lambda pair:-pair[0])
    hits=[f for score,f in ranked[:5] if score>0]
    answer=(f"Connected with {college_record.name}. What would you like to know?" if is_college_selection else "\n".join(f"{f.title}: {f.value[:700]}" for f in hits) if hits else "I don't have information about that yet.")
    assistant_msg=Message(conversation_id=conv.id,role="assistant",content=answer,source_badge="Admin Verified" if hits else "")
    db.add(assistant_msg); conv.updated_at=datetime.now(timezone.utc)
    db.add(QuestionLog(college_id=conv.college_id,raw_question=question,answer_found=bool(hits)))
    db.commit()
    return {"user_message_id":user_msg.id,"message_id":assistant_msg.id,"content":answer,"source_badge":assistant_msg.source_badge,"conversation_id":conv.id,"college_id":conv.college_id,"college_name":college_record.name if college_id and college_record else None}

@api.post("/feedback")
def submit_feedback(body:dict,u:User=Depends(current_user),db:Session=Depends(get_db)):
    message_id=body.get("message_id")
    rating=body.get("rating")
    reason=body.get("reason","")[:500]
    if not message_id or rating is None: raise HTTPException(400,"message_id and rating required")
    m=db.get(Message,message_id)
    if not m: raise HTTPException(404,"Message not found")
    fb=Feedback(message_id=message_id,rating=rating,reason=reason)
    db.add(fb); db.commit()
    return {"saved":True}

@api.get("/colleges")
def list_colleges(search:str="",db:Session=Depends(get_db)):
    query=select(College).where(College.status=="approved")
    if search: query=query.where(College.name.ilike(f"%{search}%"))
    colleges=list(db.scalars(query.order_by(College.name).limit(50)))
    return [{"id":c.id,"name":c.name,"code":c.code} for c in colleges]

@api.get("/colleges/resolve")
def resolve_college(name:str="",db:Session=Depends(get_db)):
    colleges=list(db.scalars(select(College).where(College.status=="approved")))
    college, _=fuzzy_college_resolution(name,colleges)
    if not college: raise HTTPException(404,"College not found")
    return {"id":college.id,"name":college.name,"code":college.code}

@api.get("/colleges/{college_id}")
def get_college(college_id:int,db:Session=Depends(get_db)):
    college=db.get(College,college_id)
    if not college or college.status!="approved": raise HTTPException(404,"College not found")
    return {"id":college.id,"name":college.name,"code":college.code,"data_version":college.data_version}

@api.get("/colleges/{college_id}/features")
def get_college_features(college_id:int,db:Session=Depends(get_db)):
    college=db.get(College,college_id)
    if not college: raise HTTPException(404,"College not found")
    return college.feature_flags or {"voice":True,"widget":True,"semantic_search":True}

@api.get("/colleges/{college_id}/suggestions")
def get_college_suggestions(college_id:int,db:Session=Depends(get_db)):
    gaps=list(db.scalars(select(KnowledgeGap).where(KnowledgeGap.college_id==college_id).order_by(KnowledgeGap.count.desc()).limit(10)))
    return [g.question for g in gaps]

@api.post("/registrations")
async def submit_registration(body:dict,db:Session=Depends(get_db)):
    from .models import Registration
    reg=Registration(**{k:v for k,v in body.items() if k in Registration.__annotations__})
    db.add(reg); db.commit(); db.refresh(reg)
    return {"id":reg.id,"status":"pending","development_token":secrets.token_urlsafe(8)[:12] if settings.app_env=="development" else None}

@api.get("/registrations/{registration_id}/checks")
def registration_checks(registration_id:int,db:Session=Depends(get_db)):
    from .models import Registration
    reg=db.get(Registration,registration_id)
    if not reg: raise HTTPException(404,"Registration not found")
    import socket; domain_ok=False
    try: socket.gethostbyname(reg.website.replace("https://","").replace("http://","").split("/")[0]); domain_ok=True
    except: pass
    return {"email_domain_matches":reg.contact_email.endswith(reg.website.replace("https://","").replace("http://","").split("/")[0].split(".")[-2:]),"website_reachable":domain_ok,"verification_file_matches":True,"approval_allowed":domain_ok}

@api.post("/registrations/{registration_id}/review")
def review_registration(registration_id: int, req: ReviewRegistrationRequest, db: Session = Depends(get_db), u: User = Depends(require("super_admin"))):
    from .models import Registration
    reg = db.get(Registration, registration_id)
    if not reg:
        raise HTTPException(404, "Registration not found")
    if req.decision == "approve":
        if reg.status != "pending":
            raise HTTPException(400, "Registration not pending")
        college = College(name=reg.name, code=reg.code or reg.name[:8].upper(), status="approved", data_version=1, feature_flags={"voice": True, "widget": True, "semantic_search": True})
        db.add(college); db.flush()
        admin_password = secrets.token_urlsafe(12)
        admin = User(name=reg.contact_name, email=reg.contact_email, password_hash=hash_password(admin_password), role="college_admin", college_id=college.id, email_verified=True)
        db.add(admin); reg.status = "approved"; reg.approved_by = u.id; reg.approved_at = datetime.now(timezone.utc); db.commit()
        return {"college_id": college.id, "admin_email": admin.email, "temporary_password": admin_password}
    else:
        reg.status = "rejected"; reg.reject_reason = req.reason[:500]; db.commit()
        return {"status": "rejected"}

@api.get("/super/overview")
def super_overview(db:Session=Depends(get_db),u:User=Depends(require("super_admin"))):
    pending_registrations=list(db.scalars(select(Registration).where(Registration.status=="pending").order_by(Registration.created_at.desc()).limit(500)))
    return {"colleges":db.scalar(select(func.count(College.id))),"users":db.scalar(select(func.count(User.id))),"pending":len(pending_registrations),"registrations":[{"id":r.id,"name":r.name,"status":r.status,"website":r.website,"contact_email":r.contact_email} for r in pending_registrations]}

@api.get("/admin/overview")
def admin_overview(db:Session=Depends(get_db),u:User=Depends(require("college_admin","editor","viewer"))):
    cid=u.college_id
    college=db.get(College,cid)
    college_name=college.name if college else ""
    college_code=college.code if college else ""
    lc=db.scalar(select(CrawlJob).where(CrawlJob.college_id==cid).order_by(CrawlJob.created_at.desc()).limit(1))
    lc_data={"status":lc.status,"pages_done":lc.pages_done,"pages_found":lc.pages_found,"created_at":lc.created_at.isoformat() if lc.created_at else None} if lc else None
    ps=db.scalar(select(Page.url).where(Page.college_id==cid).order_by(Page.created_at.asc()).limit(1))
    return {
        "college":college_name,
        "college_code":college_code,
        "institution_id":f"{college_code}-{cid}" if college_code else str(cid),
        "facts":db.scalar(select(func.count(Fact.id)).where(Fact.college_id==cid)),
        "pages":db.scalar(select(func.count(Page.id)).where(Page.college_id==cid)),
        "knowledge_gaps":db.scalar(select(func.count(KnowledgeGap.id)).where(KnowledgeGap.college_id==cid)),
        "questions_today":db.scalar(select(func.count(KnowledgeGap.id)).where(KnowledgeGap.college_id==cid)),
        "last_crawl":lc_data,
        "primary_source":ps or "",
        "evidence_priority":["website","document","manual"],
        "address":college.address if college else None,
        "latitude":college.latitude if college else None,
        "longitude":college.longitude if college else None,
    }

@api.post("/admin/upload")
async def admin_upload(file:UploadFile=File(...),u:User=Depends(require("college_admin","editor")),db:Session=Depends(get_db)):
    data=await file.read(10*1024*1024+1)
    if len(data)>10*1024*1024: raise HTTPException(413,"Maximum upload size is 10 MB")
    scan_upload(data)
    name=file.filename or "upload"
    suffix=name.lower().rsplit(".",1)[-1]
    text=""
    try:
        if suffix=="pdf":
            from pypdf import PdfReader
            text="\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
            if not text.strip():
                from pdf2image import convert_from_bytes
                import pytesseract
                text="\n".join(pytesseract.image_to_string(image) for image in convert_from_bytes(data,first_page=1,last_page=40))
        elif suffix=="docx":
            from docx import Document
            text="\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        elif suffix in {"xlsx","xlsm"}:
            from openpyxl import load_workbook
            wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True); text="\n".join(" | ".join(str(v) for v in row if v is not None) for ws in wb.worksheets for row in ws.iter_rows(values_only=True))
        else: raise HTTPException(415,"Upload a PDF, DOCX or XLSX document")
    except HTTPException: raise
    except Exception as e: raise HTTPException(400,f"Could not parse this document: {type(e).__name__}")
    if not text.strip(): raise HTTPException(422,"No readable text was extracted; scanned PDF OCR is not configured")
    page=Page(college_id=u.college_id,job_id=None,url="uploaded://"+name[:900],title=name[:500],raw_text=text[:2000000],content_hash=hashlib.sha256(data).hexdigest(),active=True); db.add(page); db.flush()
    fact=Fact(college_id=u.college_id,category="Uploaded Document",title=name[:300],value=text[:50000],source_page_id=page.id,confidence=.9,extra={"source_type":"uploaded document","filename":name}); db.add(fact); db.get(College,u.college_id).data_version+=1; db.commit(); return {"fact_id":fact.id,"page_id":page.id,"characters":len(text)}

@api.post("/api/v1/admin/document-upload")
async def upload_document_for_approval(file:UploadFile=File(...),db:Session=Depends(get_db),u:User=Depends(require("college_admin","editor"))):
    try:
        logger.info("document upload received filename=%r college_id=%s",file.filename,u.college_id)
        data=await file.read(20*1024*1024+1)
        if len(data)>20*1024*1024: raise HTTPException(413,"Maximum upload size is 20 MB")
        scan_upload(data)
        name=file.filename or "upload"
        suffix=name.lower().rsplit(".",1)[-1]
        content_hash=hashlib.sha256(data).hexdigest()
        existing=db.scalar(select(CollegeDocument).where(CollegeDocument.college_id==u.college_id,CollegeDocument.content_hash==content_hash))
        if existing: raise HTTPException(409,"This document has already been uploaded")
        try:
            import magic
            detected_type=magic.from_buffer(data,mime=True)
        except Exception:
            if data.startswith(b"%PDF-"):
                detected_type="application/pdf"
            elif data.startswith(b"PK\x03\x04"):
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                        names=set(archive.namelist())
                        if "word/document.xml" in names:
                            detected_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        elif "xl/workbook.xml" in names:
                            detected_type="application/vnd.ms-excel.sheet.macroenabled.12" if "xl/vbaProject.bin" in names else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        else:
                            detected_type="application/zip"
                except zipfile.BadZipFile:
                    detected_type="application/zip"
            else:
                detected_type="application/octet-stream"
        type_map={"application/pdf":"pdf","application/vnd.openxmlformats-officedocument.wordprocessingml.document":"docx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":"xlsx","application/vnd.ms-excel.sheet.macroenabled.12":"xlsm"}
        if detected_type not in type_map or type_map[detected_type]!=suffix: raise HTTPException(415,f"File type mismatch: expected {suffix}, detected {detected_type}")
        storage_dir=os.path.join("colleges",str(u.college_id),"uploads")
        os.makedirs(storage_dir,exist_ok=True)
        asset_id=uuid.uuid4().hex
        object_key=os.path.join(storage_dir,f"{asset_id}.{suffix}")
        with open(object_key,"wb") as f: f.write(data)
        doc=CollegeDocument(college_id=u.college_id,filename=name[:500],file_type=suffix,file_size_bytes=len(data),content_hash=content_hash,object_key=object_key,status="pending",submitted_by=u.id)
        db.add(doc); db.commit(); db.refresh(doc)
        from .worker import stage_document_job
        try:
            stage_document_job.delay(doc.id)
        except Exception as queue_error:
            # Keep the upload traceable, but never claim extraction started when
            # Redis/Celery did not accept the task.
            doc.status="failed"
            doc.reject_reason=f"Staging queue unavailable: {type(queue_error).__name__}"[:500]
            db.commit()
            logger.error("document staging enqueue failed document_id=%s college_id=%s error_type=%s",doc.id,u.college_id,type(queue_error).__name__)
            raise HTTPException(503,"Document was stored but staging could not start because the worker queue is unavailable") from queue_error
        logger.info("document upload stored document_id=%s college_id=%s status=pending_review filename=%r bytes=%s",doc.id,u.college_id,name,len(data))
        return {"document_id":doc.id,"status":"pending","message":"Document uploaded and staging started"}
    except HTTPException: raise
    except Exception as e:
        logger.exception("document upload failed filename=%r college_id=%s",file.filename,u.college_id)
        raise HTTPException(500,f"Document upload failed: {str(e)}") from e

@api.get("/api/v1/super-admin/pending-documents")
def list_pending_documents(db:Session=Depends(get_db),u:User=Depends(require("super_admin"))):
    docs=list(db.scalars(select(CollegeDocument).where(CollegeDocument.status=="pending").order_by(CollegeDocument.submitted_at.desc()).limit(100)))
    result=[]
    for doc in docs:
        college=db.get(College,doc.college_id)
        submitter=db.get(User,doc.submitted_by) if doc.submitted_by else None
        result.append({"id":doc.id,"college_id":doc.college_id,"college_name":college.name if college else "Unknown","filename":doc.filename,"file_type":doc.file_type,"file_size_bytes":doc.file_size_bytes,"submitted_at":doc.submitted_at.isoformat() if doc.submitted_at else None,"submitted_by":submitter.email if submitter else None,"status":doc.status,"summary":doc.summary,"rows_created":doc.rows_created})
    return {"documents":result}

@api.get("/api/v1/super-admin/documents/{document_id}")
def get_document_detail(document_id:int,db:Session=Depends(get_db),u:User=Depends(require("super_admin"))):
    doc=db.get(CollegeDocument,document_id)
    if not doc: raise HTTPException(404,"Document not found")
    college=db.get(College,doc.college_id)
    submitter=db.get(User,doc.submitted_by) if doc.submitted_by else None
    staged_rows=list(db.scalars(select(DocumentStagedRow).where(DocumentStagedRow.college_document_id==document_id,DocumentStagedRow.status=="pending").order_by(DocumentStagedRow.target_table,DocumentStagedRow.page_number)))
    rows_by_table={}
    for row in staged_rows:
        if row.target_table not in rows_by_table: rows_by_table[row.target_table]=[]
        rows_by_table[row.target_table].append({"id":row.id,"target_column":row.target_column,"page_number":row.page_number,"snippet":row.snippet,"proposed_value":row.proposed_value,"confidence":row.confidence,"row_data":row.row_data})
    staged_changes=list(db.scalars(select(DocumentStagedChange).where(DocumentStagedChange.college_document_id==document_id,DocumentStagedChange.status=="pending")))
    changes=[{"id":c.id,"change_type":c.change_type,"table_name":c.table_name,"column_name":c.column_name,"column_type":c.column_type,"proposed_schema":c.proposed_schema} for c in staged_changes]
    return {"id":doc.id,"college_id":doc.college_id,"college_name":college.name if college else "Unknown","filename":doc.filename,"file_type":doc.file_type,"file_size_bytes":doc.file_size_bytes,"content_hash":doc.content_hash,"object_key":doc.object_key,"extracted_text":doc.extracted_text[:10000] if doc.extracted_text else None,"status":doc.status,"submitted_at":doc.submitted_at.isoformat() if doc.submitted_at else None,"submitted_by":submitter.email if submitter else None,"summary":doc.summary,"rows_created":doc.rows_created,"staged_rows":rows_by_table,"staged_changes":changes}

@api.patch("/api/v1/super-admin/staged-rows/{row_id}")
def edit_staged_row(row_id:int,proposed_value:str|None=None,status:str|None=None,db:Session=Depends(get_db),u:User=Depends(require("super_admin"))):
    row=db.get(DocumentStagedRow,row_id)
    if not row: raise HTTPException(404,"Staged row not found")
    if proposed_value is not None: row.proposed_value=proposed_value[:2000]
    if status is not None and status in {"pending","removed"}: row.status=status
    db.commit()
    return {"id":row.id,"status":row.status,"proposed_value":row.proposed_value}

@api.delete("/api/v1/super-admin/staged-rows/{row_id}")
def remove_staged_row(row_id:int,db:Session=Depends(get_db),u:User=Depends(require("super_admin"))):
    row=db.get(DocumentStagedRow,row_id)
    if not row: raise HTTPException(404,"Staged row not found")
    row.status="removed"
    db.commit()
    return {"removed":True}

@api.post("/api/v1/super-admin/documents/{document_id}/approve")
def approve_document(document_id:int,db:Session=Depends(get_db),u:User=Depends(require("super_admin"))):
    doc=db.get(CollegeDocument,document_id)
    if not doc or doc.status!="pending": raise HTTPException(404,"Document not found or not pending")
    set_tenant_scope(db,doc.college_id,"super_admin",u.id)
    from .worker import approve_document_job
    try:
        approve_document_job.delay(doc.id,u.id)
    except Exception as error:
        logger.exception("document approval dispatch failed document_id=%s college_id=%s",doc.id,doc.college_id)
        raise HTTPException(503,"Approval could not be queued; the document remains pending") from error
    return {"status":"pending","message":"Approval queued. College data will update after processing completes."}

@api.post("/api/v1/super-admin/documents/{document_id}/reject")
def reject_document(document_id: int, req: RejectDocumentRequest, db: Session = Depends(get_db), u: User = Depends(require("super_admin"))):
    doc = db.get(CollegeDocument, document_id)
    if not doc or doc.status != "pending":
        raise HTTPException(404, "Document not found or not pending")
    doc.status = "rejected"; doc.reject_reason = req.reason[:500]; doc.reviewed_by = u.id; doc.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "rejected", "reason": req.reason}

@api.get("/api/v1/admin/documents")
def list_college_documents(db:Session=Depends(get_db),u:User=Depends(require("college_admin","editor"))):
    docs=list(db.scalars(select(CollegeDocument).where(CollegeDocument.college_id==u.college_id).order_by(CollegeDocument.submitted_at.desc()).limit(50)))
    return {"documents":[{"id":d.id,"filename":d.filename,"file_type":d.file_type,"status":d.status,"submitted_at":d.submitted_at.isoformat() if d.submitted_at else None,"summary":d.summary,"reject_reason":d.reject_reason} for d in docs]}

@api.post("/api/v1/admin/media")
async def upload_media(file:UploadFile=File(...),alt_text:str=Form(""),u:User=Depends(require("college_admin")),db:Session=Depends(get_db)):
    try:
        data=await file.read(10*1024*1024+1)
        if len(data)>10*1024*1024: raise HTTPException(413,"Maximum image size is 10 MB")
        scan_upload(data)
        from PIL import Image
        original=io.BytesIO(data)
        try:
            image=Image.open(original); image.verify(); original.seek(0); image=Image.open(original)
            if image.mode in {"RGBA","P"}: image=image.convert("RGB")
            thumb_image=image.copy(); thumb_image.thumbnail((640,640)); thumbnail=io.BytesIO(); thumb_image.save(thumbnail,format="WEBP",quality=78,method=5)
        except HTTPException: raise
        except Exception as exc: raise HTTPException(415,f"Unsupported or invalid image: {type(exc).__name__}")
        asset_id=uuid.uuid4().hex; object_key=f"colleges/{u.college_id}/media/{asset_id}.webp"; thumbnail_key=f"colleges/{u.college_id}/media/{asset_id}-thumb.webp"
        college=db.get(College,u.college_id); stored=db.scalar(select(func.coalesce(func.sum(MediaAsset.size_bytes),0)).where(MediaAsset.college_id==college.id)) or 0
        storage_limit=int((college.quotas or {}).get("storage_mb",1024))*1024*1024
        media_size=len(original.getvalue())+len(thumbnail.getvalue())
        if stored+media_size>storage_limit: raise HTTPException(429,"College media storage quota reached")
        try:
            from .storage import put_image,remove
            put_image(object_key,original.getvalue()); put_image(thumbnail_key,thumbnail.getvalue())
        except Exception as exc:
            try:
                from .storage import remove
                remove(object_key)
            except Exception: pass
            raise HTTPException(503,"S3-compatible media storage is unavailable") from exc
        asset=MediaAsset(college_id=u.college_id,source_url="uploaded://"+(file.filename or "image"),object_key=object_key,thumbnail_key=thumbnail_key,alt_text=alt_text[:500],content_hash=hashlib.sha256(data).hexdigest(),size_bytes=media_size); db.add(asset); college.data_version+=1
        try: db.commit(); db.refresh(asset)
        except Exception:
            db.rollback()
            try:
                from .storage import remove
                remove(object_key); remove(thumbnail_key)
            except Exception: pass
            raise
        return {"id":asset.id,"alt_text":asset.alt_text,"status":"stored"}
    except HTTPException: raise
    except Exception as e:
        import traceback
        raise HTTPException(500,f"Media upload failed: {str(e)}") from e

@api.get("/api/v1/colleges/{college_id}/media")
def college_media(college_id:int,db:Session=Depends(get_db),u:User=Depends(current_user)):
    college=db.get(College,college_id)
    if not college or college.status!="approved": raise HTTPException(404,"College not found")
    set_tenant_scope(db,college_id,u.role,u.id)
    try:
        from .storage import signed_url
        return [{"id":m.id,"alt_text":m.alt_text,"url":signed_url(m.object_key),"thumbnail_url":signed_url(m.thumbnail_key) if m.thumbnail_key else signed_url(m.object_key),"source_url":m.source_url} for m in db.scalars(select(MediaAsset).where(MediaAsset.college_id==college_id).order_by(MediaAsset.id.desc()).limit(100))]
    except Exception as exc: raise HTTPException(503,"S3-compatible media storage is unavailable") from exc

@api.delete("/api/v1/admin/media/{media_id}")
def delete_media(media_id:int,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    asset=db.get(MediaAsset,media_id)
    if not asset or asset.college_id!=u.college_id: raise HTTPException(404,"Media item not found")
    try:
        from .storage import remove
        remove(asset.object_key); remove(asset.thumbnail_key)
    except Exception as exc: raise HTTPException(503,"Object storage is unavailable; media was not removed") from exc
    college=db.get(College,u.college_id); college.data_version+=1; db.delete(asset); db.commit(); return {"deleted":True}

@api.post("/api/v1/chat/attachment")
async def chat_attachment(file: UploadFile = File(...), req: ChatAttachmentRequest = Form(None), db: Session = Depends(get_db), u: User = Depends(current_user)):
    question = req.question if req else ""
    language = req.language if req else "en-IN"
    conversation_id = req.conversation_id if req else None

    if len(question) > 2000:
        raise HTTPException(400, "Question is too long")
    conv = db.get(Conversation, conversation_id) if conversation_id else None
    if conversation_id and (not conv or conv.user_id != u.id):
        raise HTTPException(404, "Conversation not found")
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Maximum attachment size is 10 MB")
    scan_upload(data)
    name = file.filename or "attachment"
    suffix = name.lower().rsplit(".", 1)[-1]
    if suffix in {"png", "jpg", "jpeg", "webp", "gif"}:
        from PIL import Image
        try:
            img = Image.open(io.BytesIO(data))
            if img.mode in {"RGBA", "P"}:
                img = img.convert("RGB")
            out = io.BytesIO(); img.save(out, format="WEBP", quality=85); data = out.getvalue()
        except:
            raise HTTPException(415, "Invalid image")
    else:
        raise HTTPException(415, "Unsupported file type")
    if not conv:
        conv = Conversation(user_id=u.id, college_id=u.college_id, title=question[:100] or "Attachment chat")
        db.add(conv); db.flush()
    user_msg = Message(conversation_id=conv.id, role="user", content=question or f"Attached {name}")
    db.add(user_msg); db.flush()
    asset_id = uuid.uuid4().hex; object_key = f"colleges/{u.college_id}/media/{asset_id}.webp"
    from .storage import put_image
    try:
        put_image(object_key, data)
    except Exception as exc:
        raise HTTPException(503, "Media storage unavailable") from exc
    asset = MediaAsset(college_id=u.college_id, source_url="chat://attachment", object_key=object_key, alt_text=name[:500], content_hash=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
    db.add(asset); db.commit()
    answer = f"I've received your attachment {name}. What would you like to know about it?"
    assistant_msg = Message(conversation_id=conv.id, role="assistant", content=answer)
    db.add(assistant_msg); conv.updated_at = datetime.now(timezone.utc); db.commit()
    return {"message_id": assistant_msg.id, "content": answer, "conversation_id": conv.id}

@api.get("/api/v1/account/profile")
def get_account_profile(u:User=Depends(current_user)):
    return {"name":u.name,"email":u.email}

@api.patch("/api/v1/account/profile")
def update_account_profile(req: UpdateProfileRequest, u: User = Depends(current_user), db: Session = Depends(get_db)):
    u.name = req.name[:160]; db.commit()
    return {"name": u.name}

@api.get("/api/v1/account/export")
def export_account_data(u:User=Depends(current_user),db:Session=Depends(get_db)):
    convs=list(db.scalars(select(Conversation).where(Conversation.user_id==u.id)))
    msgs=[{"conversation_id":m.conversation_id,"role":m.role,"content":m.content,"created_at":m.created_at.isoformat() if m.created_at else None} for m in db.scalars(select(Message).where(Message.conversation_id.in_([c.id for c in convs])))]
    return {"user":{"id":u.id,"name":u.name,"email":u.email},"conversations":[{"id":c.id,"title":c.title,"created_at":c.created_at.isoformat() if c.created_at else None} for c in convs],"messages":msgs}

@api.delete("/api/v1/account/data")
def delete_account_data(u:User=Depends(current_user),db:Session=Depends(get_db)):
    conv_ids=[c.id for c in db.scalars(select(Conversation).where(Conversation.user_id==u.id))]
    for m in list(db.scalars(select(Message).where(Message.conversation_id.in_(conv_ids)))): db.query(Feedback).filter(Feedback.message_id==m.id).delete(synchronize_session=False)
    db.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.id.in_(conv_ids)).delete(synchronize_session=False)
    return {"deleted":True}

@api.delete("/api/v1/account/delete")
def delete_account(req: DeleteAccountRequest, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(req.password, u.password_hash):
        raise HTTPException(401, "Invalid password")
    conv_ids = [c.id for c in db.scalars(select(Conversation).where(Conversation.user_id == u.id))]
    for m in list(db.scalars(select(Message).where(Message.conversation_id.in_(conv_ids)))):
        db.query(Feedback).filter(Feedback.message_id == m.id).delete(synchronize_session=False)
    db.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.id.in_(conv_ids)).delete(synchronize_session=False)
    db.delete(u); db.commit()
    return {"deleted": True}

@api.post("/api/v1/widget/chat")
async def widget_chat(request:Request, body:dict, db:Session=Depends(get_db)):
    widget_key=request.headers.get("X-Widget-Key")
    if not widget_key: raise HTTPException(401,"Widget key required")
    college=db.scalar(select(College).where(College.widget_key==widget_key))
    if not college: raise HTTPException(401,"Invalid widget key")
    message=body.get("message","")[:2000]
    language=body.get("language","en-IN")
    if not message: raise HTTPException(400,"Message required")
    set_tenant_scope(db,college.id,"widget",None)
    question=mask_personal_data(message)
    words=[w.lower() for w in re.findall(r"\b\w+\b",question)]
    facts=list(db.scalars(select(Fact).outerjoin(Page,Fact.source_page_id==Page.id).where(Fact.college_id==college.id,Fact.confidence>0,or_(Fact.source_page_id.is_(None),Page.admin_verified==True)).limit(300)))
    ranked=sorted([(sum(w in f"{f.title} {f.category} {f.value}".lower() for w in words),f) for f in facts],key=lambda pair:-pair[0])
    hits=[f for score,f in ranked[:5] if score>0]
    answer="\n".join(f"{f.title}: {f.value[:700]}" for f in hits) if hits else "I don't have information about that yet."
    if hits:
        assets=list(db.scalars(select(MediaAsset).where(MediaAsset.college_id==college.id,MediaAsset.object_key.in_([f.source_page_id for f in hits if f.source_page_id and f.source_page_id.startswith("colleges/")]))))
        if assets:
            from .storage import signed_url
            answer="Images from this college's media library."; badge="Uploaded Document" if all(a.source_url.startswith("uploaded://") for a in assets) else "Official Website"
            sources=[{"type":"image","url":signed_url(a.object_key),"thumbnail_url":signed_url(a.thumbnail_key) if a.thumbnail_key else signed_url(a.object_key),"alt_text":a.alt_text,"source_url":a.source_url} for a in assets if a.object_key]
        else: answer="No college images are available yet."
    elif any(token in table.lower() for token in ("fee","tuition")) and not entity_terms:
        choices=sorted({f.title for f in facts if any(token in f.category.lower() for token in ("fee","tuition"))})
        if choices: answer=f"Fee information available for: {', '.join(choices[:5])}"
    conv=Conversation(user_id=None,college_id=college.id,title=message[:100])
    db.add(conv); db.flush()
    user_msg=Message(conversation_id=conv.id,role="user",content=message)
    db.add(user_msg); db.flush()
    assistant_msg=Message(conversation_id=conv.id,role="assistant",content=answer,source_badge="Admin Verified" if hits else "")
    db.add(assistant_msg); conv.updated_at=datetime.now(timezone.utc)
    db.add(QuestionLog(college_id=college.id,raw_question=question,answer_found=bool(hits)))
    db.commit()
    return JSONResponse({"answer":answer,"source_badge":assistant_msg.source_badge,"sources":locals().get("sources",[])},headers={"Access-Control-Allow-Origin":request.headers.get("Origin","*"),"Vary":"Origin"})

@api.post("/api/v1/widget/request")
def widget_request(body:dict,db:Session=Depends(get_db)):
    widget_key=body.get("widget_key")
    if not widget_key: raise HTTPException(400,"Widget key required")
    college=db.scalar(select(College).where(College.widget_key==widget_key))
    if not college: raise HTTPException(401,"Invalid widget key")
    db.add(WidgetRequest(college_id=college.id,domain=body.get("domain","")[:200],user_agent=body.get("user_agent","")[:500]))
    db.commit()
    return {"registered":True}

@api.get("/api/v1/admin/usage")
def admin_usage(db:Session=Depends(get_db),u:User=Depends(require("college_admin","editor","viewer"))):
    cid=u.college_id
    pages=db.scalar(select(func.count(Page.id)).where(Page.college_id==cid))
    media_bytes=db.scalar(select(func.coalesce(func.sum(MediaAsset.size_bytes),0)).where(MediaAsset.college_id==cid)) or 0
    ai_tokens=db.scalar(select(func.coalesce(func.sum(AIUsage.tokens),0)).where(AIUsage.college_id==cid)) or 0
    return {"pages":pages,"crawls_today":0,"media_bytes":media_bytes,"ai_tokens_this_month":ai_tokens,"quotas":{"pages":10000,"crawls_per_day":20,"storage_mb":1024,"ai_tokens_month":500000},"page_percent":round(pages/10000*100,1),"crawl_percent":0,"storage_percent":round(media_bytes/1024/1024/1024*100,1),"token_percent":round(ai_tokens/500000*100,1),"alerts":[]}

@api.get("/api/v1/admin/analytics")
def analytics(db:Session=Depends(get_db),u:User=Depends(require("college_admin","editor","viewer"))):
    cid=u.college_id
    today=datetime.now(ZoneInfo("Asia/Kolkata")).date(); first_day=today-timedelta(days=6)
    start=datetime.combine(first_day,datetime.min.time(),tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
    end=datetime.combine(today+timedelta(days=1),datetime.min.time(),tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
    base=select(QuestionLog).where(QuestionLog.college_id==cid,QuestionLog.created_at>=start,QuestionLog.created_at<end)
    rows=list(db.scalars(base.order_by(QuestionLog.created_at.desc()).limit(20000)))
    daily={ (first_day+timedelta(days=i)).isoformat():{"questions":0,"answered":0,"unanswered":0} for i in range(7)}
    topics={}
    for row in rows:
        stamp=row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        key=stamp.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
        if key in daily:
            daily[key]["questions"]+=1; daily[key]["answered"]+=int(row.answer_found); daily[key]["unanswered"]+=int(not row.answer_found)
        topic=(row.intent or "Other").strip() or "Other"; topics[topic]=topics.get(topic,0)+1
    feedback_rows=list(db.scalars(select(Feedback).join(Message,Feedback.message_id==Message.id).join(Conversation,Message.conversation_id==Conversation.id).where(Conversation.college_id==cid)))
    positive=sum(1 for item in feedback_rows if item.rating>0); satisfaction=round(positive/len(feedback_rows)*100,1) if feedback_rows else None
    response_times=[row.response_ms for row in rows if row.response_ms]
    p95=sorted(response_times)[int(len(response_times)*0.95)] if response_times else None
    slow=[{"question":row.raw_question[:200],"response_ms":row.response_ms} for row in rows if row.response_ms and row.response_ms>5000][:10]
    return {"questions_today":daily.get(today.isoformat(),{}).get("questions",0),"unanswered_week":sum(d["unanswered"] for d in daily.values()),"satisfaction_percent":satisfaction,"p95_response_ms":p95,"daily":daily,"top_topics":sorted(topics.items(),key=lambda x:-x[1])[:10],"slow_answers":slow,"feedback_total":len(feedback_rows)}

@api.get("/api/v1/admin/widget")
def get_widget_settings(db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    college=db.get(College,u.college_id)
    if not college: raise HTTPException(404,"College not found")
    return {"allowed_domains":college.allowed_domains or [],"feature_flags":college.feature_flags or {"voice":True,"widget":True,"semantic_search":True},"embed_script":f'<script src="{settings.public_base_url}/widget.js" data-key="{college.widget_key or ""}"></script>'}

@api.patch("/api/v1/admin/college-settings")
def update_college_settings(body:dict,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    college=db.get(College,u.college_id)
    if not college: raise HTTPException(404,"College not found")
    if "allowed_domains" in body: college.allowed_domains=body["allowed_domains"]
    if "feature_flags" in body: college.feature_flags=body["feature_flags"]
    college.data_version+=1; db.commit()
    return {"updated":True}

@api.get("/api/v1/admin/crawl-schedule")
def get_crawl_schedule(db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    schedule=db.scalar(select(CrawlSchedule).where(CrawlSchedule.college_id==u.college_id))
    return {"enabled":bool(schedule and schedule.enabled),"url":schedule.url if schedule else ""}

@api.put("/api/v1/admin/crawl-schedule")
def update_crawl_schedule(body:dict,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    enabled=body.get("enabled",False)
    url=body.get("url","")[:500]
    schedule=db.scalar(select(CrawlSchedule).where(CrawlSchedule.college_id==u.college_id))
    if not schedule:
        schedule=CrawlSchedule(college_id=u.college_id,url=url,enabled=enabled,interval_days=7,next_run_at=datetime.now(timezone.utc))
        db.add(schedule)
    else:
        schedule.enabled=enabled; schedule.url=url
    db.commit()
    return {"enabled":enabled,"url":url}

@api.post("/api/v1/admin/crawl")
def start_crawl(body:dict,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    url=body.get("url","")[:500]
    if not url: raise HTTPException(400,"URL required")
    from .crawler import crawl_college
    try:
        job_id=crawl_college(u.college_id,url)
        return {"status":"started","id":job_id}
    except ValueError as e:
        raise HTTPException(400,str(e)) from e
    except RuntimeError as e:
        raise HTTPException(503,str(e)) from e
    except Exception as e:
        logger.exception("crawl dispatch failed college_id=%s",u.college_id)
        raise HTTPException(500,f"Crawl failed to start: {str(e)}") from e

@api.get("/api/v1/admin/sources")
def list_sources(db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    sources=list(db.scalars(select(CollegeSource).where(CollegeSource.college_id==u.college_id)))
    return [{"id":s.id,"url":s.url,"type":s.type,"priority":s.priority,"campus":s.campus} for s in sources]

@api.post("/api/v1/admin/sources")
def add_source(body:dict,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    source=CollegeSource(college_id=u.college_id,url=body.get("url","")[:500],type=body.get("type","department site")[:40],priority=body.get("priority",2),campus=body.get("campus","")[:180])
    db.add(source); db.commit()
    return {"id":source.id}

@api.delete("/api/v1/admin/sources/{source_id}")
def delete_source(source_id:int,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    source=db.get(CollegeSource,source_id)
    if not source or source.college_id!=u.college_id: raise HTTPException(404,"Source not found")
    db.delete(source); db.commit()
    return {"deleted":True}

@api.get("/api/v1/admin/knowledge-gaps")
def list_knowledge_gaps(db:Session=Depends(get_db),u:User=Depends(require("college_admin","editor"))):
    gaps=list(db.scalars(select(KnowledgeGap).where(KnowledgeGap.college_id==u.college_id).order_by(KnowledgeGap.count.desc()).limit(50)))
    return [{"id":g.id,"question":g.question,"count":g.count} for g in gaps]

@api.post("/api/v1/admin/knowledge-gaps/{gap_id}/answer")
def answer_knowledge_gap(gap_id:int,body:dict,db:Session=Depends(get_db),u:User=Depends(require("college_admin","editor"))):
    gap=db.get(KnowledgeGap,gap_id)
    if not gap or gap.college_id!=u.college_id: raise HTTPException(404,"Gap not found")
    fact=Fact(college_id=u.college_id,category=body.get("category","general")[:100],title=body.get("title",gap.question)[:300],value=body.get("value","")[:50000],confidence=0.9)
    db.add(fact); db.delete(gap); db.commit()
    return {"answered":True}

@api.get("/api/v1/admin/custom-fields")
def list_custom_fields(db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    fields=list(db.scalars(select(CustomField).where(CustomField.college_id==u.college_id)))
    return [{"id":f.id,"table_name":f.table_name,"field_name":f.field_name,"field_type":f.field_type} for f in fields]

@api.post("/api/v1/admin/custom-fields")
def add_custom_field(body:dict,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    field=CustomField(college_id=u.college_id,table_name=body.get("table_name","other_facts")[:100],field_name=body.get("field_name","")[:100],field_type=body.get("field_type","text")[:50])
    db.add(field); db.commit()
    return {"id":field.id}

@api.get("/api/v1/admin/members")
def list_members(db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    members=list(db.scalars(select(User).where(User.college_id==u.college_id)))
    return [{"id":m.id,"name":m.name,"email":m.email,"role":m.role} for m in members]

@api.delete("/api/v1/admin/members/{member_id}")
def remove_member(member_id:int,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    member=db.get(User,member_id)
    if not member or member.college_id!=u.college_id: raise HTTPException(404,"Member not found")
    member.college_id=None; member.role="user"; db.commit()
    return {"removed":True}

@api.post("/api/v1/admin/invitations")
def create_invitation(body:dict,db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    invite=CollegeInvitation(college_id=u.college_id,email=body.get("email","")[:255],role=body.get("role","editor"))
    db.add(invite); db.commit()
    return {"id":invite.id,"development_token":secrets.token_urlsafe(8)[:12] if settings.app_env=="development" else None}

@api.get("/api/v1/admin/college-export")
def college_export(db:Session=Depends(get_db),u:User=Depends(require("college_admin"))):
    return {"college_id":u.college_id,"facts":[{"category":f.category,"title":f.title,"value":f.value,"extra":f.extra} for f in db.scalars(select(Fact).where(Fact.college_id==u.college_id))],"pages":[{"url":p.url,"title":p.title,"content_hash":p.content_hash} for p in db.scalars(select(Page).where(Page.college_id==u.college_id))]}

@api.post("/api/v1/super/support-view")
def support_view(body:dict,db:Session=Depends(get_db),u:User=Depends(require("super_admin"))):
    cid=int(body.get("college_id",0)); reason=str(body.get("reason", ""))[:1000]
    if not reason or not db.get(College,cid): raise HTTPException(400,"College and support reason are required")
    db.add(AuditLog(actor_id=u.id,college_id=cid,action="support.view.read_only",target=str(cid),after={"reason":reason,"expires_in_minutes":15})); db.commit()
    return {"mode":"read_only","expires_in_minutes":15,"overview":{"facts":db.scalar(select(func.count(Fact.id)).where(Fact.college_id==cid)),"pages":db.scalar(select(func.count(Page.id)).where(Fact.college_id==cid))}}

def scan_upload(data:bytes):
    if settings.clamav_host and settings.clamav_port:
        try:
            import pyclamd
            cd=pyclamd.ClamdNetworkClient(settings.clamav_host,settings.clamav_port)
            if cd.scan_stream(data): raise HTTPException(422,"File infected with malware")
        except HTTPException:
            raise
        except Exception:
            # If ClamAV is unavailable, fail closed for security
            raise HTTPException(503,"Malware scanner unavailable; cannot process upload")
