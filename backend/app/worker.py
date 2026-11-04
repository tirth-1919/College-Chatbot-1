from celery import Celery
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, delete
from email.message import EmailMessage
import smtplib
import io, hashlib, os, re
import logging
from pathlib import Path
from .db import SessionLocal, set_tenant_scope
from .models import CrawlJob, CrawlSchedule, College, Page, PageChunk, Notification, User, CollegeDocument, DocumentStagedRow, DocumentStagedChange, Program, Fee, Faculty, Department, Facility, Hostel, Placement, Scholarship, Event, Library, Fact, CustomTable, CustomField, CustomTableRow, KnowledgeCatalog, AnswerCache, AuditLog
from .config import settings
_local_file_broker = settings.redis_url.startswith("filesystem://")
celery = Celery(
    "chatbot",
    broker=settings.redis_url,
    backend=None if _local_file_broker else settings.redis_url,
)
if _local_file_broker:
    # Kombu's filesystem transport is useful for local Windows development
    # where Redis is not installed. Both producer and worker share this queue.
    _queue_dir = Path("runtime/celery-queue").resolve()
    _processed_dir = _queue_dir / "processed"
    _control_dir = _queue_dir / "control"
    for _directory in (_queue_dir, _processed_dir, _control_dir):
        _directory.mkdir(parents=True, exist_ok=True)
    celery.conf.update(
        broker_transport_options={
            "data_folder_in": str(_queue_dir),
            "data_folder_out": str(_queue_dir),
            "store_processed": True,
            "processed_folder": str(_processed_dir),
            "control_folder": str(_control_dir),
        },
        task_ignore_result=True,
    )
logger=logging.getLogger(__name__)
celery.conf.task_acks_late = True
celery.conf.task_reject_on_worker_lost = True
celery.conf.beat_schedule = {
    "enqueue-due-college-crawls": {"task": "app.worker.enqueue_due_crawls", "schedule": 60.0},
    "deliver-admin-notifications": {"task": "app.worker.enqueue_unsent_notifications", "schedule": 60.0},
}

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def deliver_notification(self, notification_id: int):
    db=SessionLocal()
    try:
        set_tenant_scope(db,None,"super_admin",0)
        notice=db.scalar(select(Notification).where(Notification.id==notification_id).with_for_update())
        if not notice or notice.email_sent_at or not settings.smtp_host: return {"sent":False}
        college=db.get(College,notice.college_id)
        admins=list(db.scalars(select(User).where(User.college_id==notice.college_id,User.role=="college_admin",User.email_verified==True)))
        recipients=sorted({user.email for user in admins if user.email}|({college.email} if college and college.email else set()))
        if not recipients: return {"sent":False,"reason":"no verified admin recipient"}
        with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=12) as smtp:
            smtp.starttls()
            if settings.smtp_user: smtp.login(settings.smtp_user,settings.smtp_password)
            for recipient in recipients:
                message=EmailMessage(); message["Subject"]=f"{college.name if college else 'College FAQ'}: {notice.title}"; message["From"]=settings.smtp_from; message["To"]=recipient
                message.set_content(f"{notice.title}\n\n{notice.body}\n\nOpen the college admin dashboard to review this notification.")
                smtp.send_message(message)
        notice.email_sent_at=datetime.now(timezone.utc); db.commit()
        return {"sent":True,"recipients":len(recipients)}
    except Exception:
        db.rollback(); raise
    finally: db.close()

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def enqueue_unsent_notifications(self):
    if not settings.smtp_host: return {"enqueued":0}
    db=SessionLocal()
    try:
        set_tenant_scope(db,None,"super_admin",0)
        ids=list(db.scalars(select(Notification.id).where(Notification.email_sent_at.is_(None)).order_by(Notification.id).limit(100)))
        for notification_id in ids: deliver_notification.delay(notification_id)
        return {"enqueued":len(ids)}
    finally: db.close()

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=4)
def crawl_task(self, job_id: int):
    from .crawler import run_crawl
    return run_crawl(job_id)

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def enqueue_due_crawls(self):
    db=SessionLocal(); now=datetime.now(timezone.utc); jobs=[]
    try:
        set_tenant_scope(db,None,"super_admin",0)
        schedules=list(db.scalars(select(CrawlSchedule).where(CrawlSchedule.enabled==True,CrawlSchedule.next_run_at<=now).order_by(CrawlSchedule.next_run_at).with_for_update(skip_locked=True).limit(50)))
        for schedule in schedules:
            college=db.get(College,schedule.college_id)
            if not college or college.status!="approved":
                schedule.enabled=False
                continue
            quotas=college.quotas or {}
            pages=db.scalar(select(func.count(Page.id)).where(Page.college_id==college.id)) or 0
            today=datetime.now(ZoneInfo("Asia/Kolkata")).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
            crawls_today=db.scalar(select(func.count(CrawlJob.id)).where(CrawlJob.college_id==college.id,CrawlJob.created_at>=today)) or 0
            if pages>=int(quotas.get("pages",10000)) or crawls_today>=int(quotas.get("crawls_per_day",20)):
                schedule.next_run_at=now+timedelta(days=1)
                continue
            schedule.last_run_at=now; schedule.next_run_at=now+timedelta(days=schedule.interval_days)
            set_tenant_scope(db,college.id,"worker")
            job=CrawlJob(college_id=college.id,url=schedule.url,status="queued",version=college.data_version+1); db.add(job); db.flush(); jobs.append(job.id)
            set_tenant_scope(db,None,"super_admin",0)
        db.commit()
        for job_id in jobs: crawl_task.delay(job_id)
        return {"enqueued":len(jobs)}
    except Exception:
        db.rollback(); raise
    finally:
        db.close()

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def stage_document_job(self, document_id: int):
    db=SessionLocal()
    try:
        doc=db.get(CollegeDocument,document_id)
        if not doc or doc.status!="pending": return {"staged":False,"reason":"document not pending"}
        logger.info("document extraction started document_id=%s college_id=%s filename=%r",doc.id,doc.college_id,doc.filename)
        set_tenant_scope(db,doc.college_id,"worker")
        if not os.path.exists(doc.object_key):
            doc.status="failed"; doc.reject_reason="File not found"; db.commit()
            return {"staged":False,"reason":"file not found"}
        with open(doc.object_key,"rb") as f: data=f.read()
        text=""
        suffix=doc.file_type
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
                wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True)
                text="\n".join(" | ".join(str(v) for v in row if v is not None) for ws in wb.worksheets for row in ws.iter_rows(values_only=True))
            else:
                doc.status="failed"; doc.reject_reason=f"Unsupported file type: {suffix}"; db.commit()
                return {"staged":False,"reason":"unsupported file type"}
        except Exception as e:
            doc.status="failed"; doc.reject_reason=f"Extraction error: {type(e).__name__}"; db.commit()
            return {"staged":False,"reason":str(e)}
        if not text.strip():
            doc.status="failed"; doc.reject_reason="No readable text extracted"; db.commit()
            return {"staged":False,"reason":"no text extracted"}
        doc.extracted_text=text[:5000000]
        tables=[]
        if suffix=="pdf":
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(data)) as pdf:
                    for page_num,page in enumerate(pdf.pages[:100],1):
                        for table in page.extract_tables():
                            if table and any(row for row in table if any(cell for cell in row if cell)):
                                tables.append({"page":page_num,"headers":table[0] if table else [],"rows":table[1:] if len(table)>1 else []})
            except ImportError:
                pass
        table_count=0
        row_count=0
        for table_info in tables[:50]:
            if not table_info["headers"] or not table_info["rows"]: continue
            table_text=" ".join(" ".join(str(cell) or "" for cell in row) for row in [table_info["headers"]]+table_info["rows"])
            if not table_text.strip(): continue
            from .providers import ask_ai
            prompt=f"""Analyze this table and determine which data category it belongs to. Respond with strict JSON only, no markdown:
            Categories: programs, fees, faculty, departments, facilities, hostel, placements, scholarships, events, library, other_facts
            Table headers: {table_info["headers"]}
            Sample rows: {table_info["rows"][:3]}
            Respond in this exact JSON format: {{"category":"category_name","confidence":0.8,"reason":"explanation"}}"""
            try:
                response=ask_ai(prompt,temperature=0.1)
                import json
                result=json.loads(response)
                category=result.get("category","other_facts")
                confidence=float(result.get("confidence",0.5))
            except:
                category="other_facts"; confidence=0.3
            if category not in {"programs","fees","faculty","departments","facilities","hostel","placements","scholarships","events","library","other_facts"}:
                category="other_facts"
            for row in table_info["rows"][:20]:
                if not any(row): continue
                row_text=" | ".join(str(cell) or "" for cell in row)
                if not row_text.strip(): continue
                for value in row:
                    if value and str(value).strip() and str(value).strip() in text:
                        staged=DocumentStagedRow(college_document_id=doc.id,college_id=doc.college_id,target_table=category,page_number=table_info["page"],snippet=row_text[:500],proposed_value=str(value)[:2000],confidence=confidence,row_data={"headers":table_info["headers"],"row":row},status="pending")
                        db.add(staged); row_count+=1
            table_count+=1
        if row_count==0:
            db.add(DocumentStagedRow(college_document_id=doc.id,college_id=doc.college_id,target_table="other_facts",page_number=1,snippet=text[:500],proposed_value=doc.filename[:2000],confidence=0.5,row_data={"text":text[:50000]},status="pending"))
            row_count=1
        doc.summary=f"Extracted {len(text)} characters, found {table_count} tables, staged {row_count} rows"
        doc.rows_created=row_count
        db.commit()
        logger.info("document extraction complete document_id=%s college_id=%s characters=%s tables=%s staged_rows=%s status=pending_review",doc.id,doc.college_id,len(text),table_count,row_count)
        return {"staged":True,"tables":table_count,"rows":row_count}
    except Exception:
        logger.exception("document extraction/index staging failed document_id=%s",document_id)
        db.rollback(); raise
    finally:
        db.close()

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def approve_document_job(self, document_id: int, reviewer_id: int):
    db=SessionLocal()
    try:
        doc=db.get(CollegeDocument,document_id)
        if not doc or doc.status!="pending": return {"approved":False,"reason":"document not pending"}
        set_tenant_scope(db,doc.college_id,"super_admin",reviewer_id)
        source_page=Page(
            college_id=doc.college_id,
            url=f"uploaded://document/{doc.id}/{doc.filename}",
            title=doc.filename[:500],
            raw_text=doc.extracted_text or "",
            content_hash=doc.content_hash,
            admin_verified=True,
            active=True,
        )
        db.add(source_page); db.flush()
        table_map={"programs":Program,"fees":Fee,"faculty":Faculty,"departments":Department,"facilities":Facility,"hostel":Hostel,"placements":Placement,"scholarships":Scholarship,"events":Event,"library":Library,"other_facts":Fact}
        staged_rows=list(db.scalars(select(DocumentStagedRow).where(DocumentStagedRow.college_document_id==document_id,DocumentStagedRow.status=="pending")))
        rows_inserted=0
        for staged in staged_rows:
            target_class=table_map.get(staged.target_table)
            if not target_class: continue
            row_data=staged.row_data or {}
            headers=row_data.get("headers") or []
            values=row_data.get("row") or []
            searchable_value=row_data.get("text") or " | ".join(f"{headers[i]}: {value}" if i<len(headers) else str(value) for i,value in enumerate(values)) or staged.snippet or staged.proposed_value or ""
            fact_category=f"uploaded {staged.target_table}"[:100]
            fact_title=(staged.proposed_value or "Extracted Data")[:300]
            existing_fact=db.scalar(select(Fact).where(Fact.college_id==doc.college_id,Fact.category==fact_category,Fact.title==fact_title,Fact.source_page_id==source_page.id))
            if staged.target_table=="other_facts":
                row=existing_fact or target_class(college_id=doc.college_id,category=fact_category,title=fact_title,value=searchable_value[:50000],source_page_id=source_page.id,confidence=staged.confidence,extra={"source_document_id":doc.id,"page_number":staged.page_number,"snippet":staged.snippet})
            else:
                row=target_class(college_id=doc.college_id,source_page_id=source_page.id,source_document_id=doc.id,title=fact_title,data={"value":staged.proposed_value,"source_page":staged.page_number,"snippet":staged.snippet,"row":row_data},confidence=staged.confidence,source_sections=[])
                db.add(row)
                if not existing_fact:
                    db.add(Fact(college_id=doc.college_id,category=fact_category,title=fact_title,value=searchable_value[:50000],source_page_id=source_page.id,confidence=staged.confidence,extra={"source_type":"uploaded document","source_document_id":doc.id,"page_number":staged.page_number,"filename":doc.filename}))
            db.add(row); db.flush()
            rows_inserted+=1
            staged.status="approved"
            if staged.target_table=="other_facts":
                if not existing_fact:
                    from .models import FactHistory
                    history=FactHistory(fact_id=row.id,college_id=doc.college_id,category=row.category,title=row.title,value=row.value,extra=row.extra,changed_by=reviewer_id,changed_via="document_approval")
                    db.add(history)
        for change in list(db.scalars(select(DocumentStagedChange).where(DocumentStagedChange.college_document_id==document_id,DocumentStagedChange.status=="pending"))):
            if change.change_type=="new_table":
                existing=db.scalar(select(CustomTable).where(CustomTable.college_id==doc.college_id,CustomTable.table_slug==change.table_name))
                if not existing:
                    safe_slug=re.sub(r"[^a-z0-9_]+","_",change.table_name.lower())[:80]
                    table_count=db.scalar(select(func.count(CustomTable.id)).where(CustomTable.college_id==doc.college_id)) or 0
                    if table_count<20:
                        new_table=CustomTable(college_id=doc.college_id,table_slug=safe_slug,display_name=change.table_name[:240],description=f"Created from document upload: {doc.filename}",schema=change.proposed_schema,source_document_id=doc.id)
                        db.add(new_table); db.flush()
                        audit=AuditLog(actor_id=reviewer_id,college_id=doc.college_id,action="create_custom_table",target=f"custom_tables:{new_table.id}",before={},after={"table_slug":safe_slug,"display_name":change.table_name,"source_document_id":doc.id})
                        db.add(audit)
                change.status="approved"
            elif change.change_type=="new_column":
                existing=db.scalar(select(CustomField).where(CustomField.college_id==doc.college_id,CustomField.table_name==change.table_name,CustomField.field_name==change.column_name))
                if not existing:
                    new_field=CustomField(college_id=doc.college_id,table_name=change.table_name[:80],field_name=change.column_name[:80],field_type=change.column_type or "text")
                    db.add(new_field); db.flush()
                    audit=AuditLog(actor_id=reviewer_id,college_id=doc.college_id,action="add_custom_field",target=f"{change.table_name}.{change.column_name}",before={},after={"table_name":change.table_name,"field_name":change.column_name,"field_type":change.column_type})
                    db.add(audit)
                change.status="approved"
        college=db.get(College,doc.college_id)
        college.data_version+=1
        db.execute(delete(AnswerCache).where(AnswerCache.college_id==doc.college_id))
        doc.rows_created=rows_inserted
        doc.status="approved"
        doc.reviewed_by=reviewer_id
        doc.reviewed_at=datetime.now(timezone.utc)
        audit=AuditLog(actor_id=reviewer_id,college_id=doc.college_id,action="approve_document",target=f"college_documents:{doc.id}",before={"status":"pending","rows_created":0},after={"status":"approved","rows_created":rows_inserted})
        db.add(audit)
        db.commit()
        return {"approved":True,"rows_inserted":rows_inserted,"data_version":college.data_version}
    except Exception:
        db.rollback(); raise
    finally:
        db.close()

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def rollback_document_job(self, document_id: int, reviewer_id: int):
    db=SessionLocal()
    try:
        doc=db.get(CollegeDocument,document_id)
        if not doc or doc.status!="approved": return {"rolled_back":False,"reason":"document not approved"}
        set_tenant_scope(db,doc.college_id,"super_admin",reviewer_id)
        source_page=db.scalar(select(Page).where(Page.college_id==doc.college_id,Page.url==f"uploaded://document/{doc.id}/{doc.filename}"))
        table_map={"programs":Program,"fees":Fee,"faculty":Faculty,"departments":Department,"facilities":Facility,"hostel":Hostel,"placements":Placement,"scholarships":Scholarship,"events":Event,"library":Library,"other_facts":Fact}
        rows_removed=0
        for table_name,model_class in table_map.items():
            if table_name=="other_facts":
                rows=list(db.scalars(select(Fact).where(Fact.college_id==doc.college_id,Fact.source_page_id==source_page.id))) if source_page else []
            else:
                rows=list(db.scalars(select(model_class).where(model_class.source_document_id==document_id)))
            for row in rows:
                if table_name=="other_facts":
                    db.execute(delete(KnowledgeCatalog).where(KnowledgeCatalog.fact_id==row.id))
                db.delete(row); rows_removed+=1
        custom_tables=list(db.scalars(select(CustomTable).where(CustomTable.source_document_id==document_id)))
        tables_removed=0
        for table in custom_tables:
            row_count=db.scalar(select(func.count(CustomTableRow.id)).where(CustomTableRow.custom_table_id==table.id)) or 0
            db.execute(delete(CustomTableRow).where(CustomTableRow.custom_table_id==table.id))
            db.delete(table); tables_removed+=1
        custom_fields=list(db.scalars(select(CustomField).where(CustomField.table_name.in_(select(CustomTable.table_slug).where(CustomTable.source_document_id==document_id)))))
        fields_removed=0
        for field in custom_fields:
            db.delete(field); fields_removed+=1
        if source_page:
            db.execute(delete(PageChunk).where(PageChunk.page_id==source_page.id))
            db.delete(source_page)
        college=db.get(College,doc.college_id)
        college.data_version+=1
        db.execute(delete(AnswerCache).where(AnswerCache.college_id==doc.college_id))
        previous_rows=doc.rows_created; doc.status="rolled_back"; doc.rows_created=0
        audit=AuditLog(actor_id=reviewer_id,college_id=doc.college_id,action="rollback_document",target=f"college_documents:{doc.id}",before={"status":"approved","rows_created":previous_rows},after={"status":"rolled_back","rows_removed":rows_removed})
        db.add(audit)
        db.commit()
        return {"rolled_back":True,"rows_removed":rows_removed,"tables_removed":tables_removed,"fields_removed":fields_removed}
    except Exception:
        db.rollback(); raise
    finally:
        db.close()
