import hashlib
import uuid

from docx import Document as DocxDocument
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    AnswerCache,
    AuditLog,
    College,
    CollegeDocument,
    DocumentStagedRow,
    Fact,
    KnowledgeCatalog,
    Page,
    Program,
    User,
)
from app import worker
from app.worker import approve_document_job, stage_document_job


def test_text_only_docx_can_be_staged_approved_and_rolled_back(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", test_session)
    db = test_session()
    suffix = uuid.uuid4().hex[:12]
    source_file = tmp_path / "programs.docx"
    word = DocxDocument()
    word.add_paragraph("BCA is a three-year program offered by this college.")
    word.save(source_file)
    file_bytes = source_file.read_bytes()
    college = College(name="Approval Test College", code=f"DOC-{suffix.upper()}")
    reviewer = User(
        name="Approval Reviewer",
        email=f"reviewer-{suffix}@example.test",
        password_hash="not-used-in-this-test",
        role="super_admin",
        email_verified=True,
    )
    try:
        db.add_all([college, reviewer])
        db.flush()
        document = CollegeDocument(
            college_id=college.id,
            filename="programs.docx",
            file_type="docx",
            file_size_bytes=len(file_bytes),
            content_hash=hashlib.sha256(file_bytes).hexdigest(),
            object_key=str(source_file),
            status="pending",
        )
        db.add(document)
        db.flush()
        db.commit()
        document_id, reviewer_id, college_id = document.id, reviewer.id, college.id

        staged_result = stage_document_job.run(document_id)
        db.expire_all()
        assert staged_result["staged"] is True and staged_result["rows"] == 1
        document = db.get(CollegeDocument, document_id)
        assert document.status == "pending"
        assert "BCA is a three-year program" in document.extracted_text
        db.add(DocumentStagedRow(
            college_document_id=document.id,
            college_id=college.id,
            target_table="programs",
            page_number=1,
            snippet="BCA | Three years",
            proposed_value="BCA",
            confidence=0.9,
            status="pending",
            row_data={"headers": ["Program", "Duration"], "row": ["BCA", "Three years"]},
        ))
        db.commit()

        result = approve_document_job.run(document_id, reviewer_id)

        db.expire_all()
        program = db.scalar(select(Program).where(Program.source_document_id == document_id))
        fact = db.scalar(select(Fact).where(Fact.college_id == college_id, Fact.category == "uploaded programs"))
        text_fact = db.scalar(select(Fact).where(Fact.college_id == college_id, Fact.category == "uploaded other_facts"))
        assert result["approved"] is True
        assert program is not None and program.source_page_id is not None
        assert fact is not None and fact.source_page_id == program.source_page_id
        assert text_fact is not None and "BCA is a three-year program" in text_fact.value
        assert db.scalar(select(KnowledgeCatalog.id).where(KnowledgeCatalog.fact_id == fact.id)) is not None

        rollback = worker.rollback_document_job.run(document_id, reviewer_id)
        db.expire_all()
        assert rollback["rolled_back"] is True
        assert db.scalar(select(Fact).where(Fact.college_id == college_id)) is None
        assert db.scalar(select(Program).where(Program.source_document_id == document_id)) is None
    finally:
        if college.id:
            db.query(AnswerCache).filter(AnswerCache.college_id == college.id).delete(synchronize_session=False)
            db.query(KnowledgeCatalog).filter(KnowledgeCatalog.college_id == college.id).delete(synchronize_session=False)
            db.query(Fact).filter(Fact.college_id == college.id).delete(synchronize_session=False)
            db.query(Program).filter(Program.college_id == college.id).delete(synchronize_session=False)
            db.query(DocumentStagedRow).filter(DocumentStagedRow.college_id == college.id).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.college_id == college.id).delete(synchronize_session=False)
            db.query(CollegeDocument).filter(CollegeDocument.college_id == college.id).delete(synchronize_session=False)
            db.query(Page).filter(Page.college_id == college.id).delete(synchronize_session=False)
            db.delete(college)
        if reviewer.id:
            db.delete(reviewer)
        db.commit()
        db.close()
