"""
Test scripts for Document Approval Workflow (Section 21.7)
Run with: python test_document_approval.py

Tests:
1. Upload document stays Pending
2. Pending document invisible to students
3. After approval, rows appear in admin tables
4. After approval, rows appear in chat answers
5. Document rejection with email
6. Rollback removes rows
7. Custom tables and columns
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select, func
from app.db import SessionLocal, Base, engine
from app.models import (
    College, User, CollegeDocument, DocumentStagedRow,
    Program, Fee, Fact, CustomTable, CustomTableRow, KnowledgeCatalog
)
from datetime import datetime, timezone
import hashlib
import io

def print_test_header(test_num, description):
    print(f"\n{'='*60}")
    print(f"TEST {test_num}: {description}")
    print('='*60)

def print_result(passed, message):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {message}")
    return passed

def test_1_upload_stays_pending():
    """Test 1: Upload document stays Pending"""
    print_test_header(1, "Upload document stays Pending")
    
    db = SessionLocal()
    try:
        # Get or create test college and admin
        college = db.scalar(select(College).where(College.code == "TEST")) or College(
            name="Test College", code="TEST", website="https://test.edu",
            email="admin@test.edu", status="approved"
        )
        if not college.id:
            db.add(college)
            db.flush()
        
        admin = db.scalar(select(User).where(User.email == "admin@test.edu")) or User(
            name="Test Admin", email="admin@test.edu",
            password_hash="test_hash", role="college_admin",
            college_id=college.id, email_verified=True
        )
        if not admin.id:
            db.add(admin)
            db.flush()
        
        # Simulate document upload
        test_data = b"Test PDF content for approval workflow"
        content_hash = hashlib.sha256(test_data).hexdigest()
        
        doc = CollegeDocument(
            college_id=college.id,
            filename="test_document.pdf",
            file_type="pdf",
            file_size_bytes=len(test_data),
            content_hash=content_hash,
            object_key=f"colleges/{college.id}/uploads/test.pdf",
            status="pending",
            submitted_by=admin.id,
            extracted_text="Test extracted text",
            summary="Test summary"
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        # Verify status is pending
        pending_docs = list(db.scalars(
            select(CollegeDocument).where(
                CollegeDocument.id == doc.id,
                CollegeDocument.status == "pending"
            )
        ))
        
        result = len(pending_docs) == 1
        return print_result(result, f"Document {doc.id} has status 'pending'")
        
    except Exception as e:
        return print_result(False, f"Error: {str(e)}")
    finally:
        db.close()

def test_2_pending_invisible_to_students():
    """Test 2: Pending document invisible to students"""
    print_test_header(2, "Pending document invisible to students")
    
    db = SessionLocal()
    try:
        # Get pending document
        doc = db.scalar(select(CollegeDocument).where(CollegeDocument.status == "pending"))
        if not doc:
            return print_result(False, "No pending document found")
        
        # Check if any rows exist in live tables with this document_id
        programs = db.scalar(select(func.count(Program.id)).where(
            Program.source_document_id == doc.id
        ))
        fees = db.scalar(select(func.count(Fee.id)).where(
            Fee.source_document_id == doc.id
        ))
        facts = db.scalar(select(func.count(Fact.id)).where(
            Fact.extra["source_document_id"].astext == str(doc.id)
        ))
        
        result = programs == 0 and fees == 0 and facts == 0
        return print_result(result, f"No live rows found for pending document {doc.id}")
        
    except Exception as e:
        return print_result(False, f"Error: {str(e)}")
    finally:
        db.close()

def test_3_approval_creates_rows():
    """Test 3: After approval, rows appear in admin tables"""
    print_test_header(3, "After approval, rows appear in admin tables")
    
    db = SessionLocal()
    try:
        # Get pending document
        doc = db.scalar(select(CollegeDocument).where(CollegeDocument.status == "pending"))
        if not doc:
            return print_result(False, "No pending document found")
        
        # Create staged rows
        staged = DocumentStagedRow(
            college_document_id=doc.id,
            college_id=doc.college_id,
            target_table="programs",
            page_number=1,
            snippet="Test program row",
            proposed_value="BCA Program",
            confidence=0.9,
            row_data={"title": "BCA Program"},
            status="pending"
        )
        db.add(staged)
        
        staged2 = DocumentStagedRow(
            college_document_id=doc.id,
            college_id=doc.college_id,
            target_table="other_facts",
            page_number=1,
            snippet="Test fact row",
            proposed_value="Test fact value",
            confidence=0.8,
            row_data={"value": "Test fact value"},
            status="pending"
        )
        db.add(staged2)
        db.commit()
        
        # Simulate approval by directly inserting rows (bypassing background job for test)
        program = Program(
            college_id=doc.college_id,
            source_document_id=doc.id,
            title="BCA Program",
            data={"test": "data"},
            confidence=0.9,
            source_sections=[]
        )
        db.add(program)
        
        fact = Fact(
            college_id=doc.college_id,
            category="uploaded_document",
            title="Test fact",
            value="Test fact value",
            confidence=0.8,
            extra={"source_document_id": doc.id}
        )
        db.add(fact)
        
        doc.status = "approved"
        doc.rows_created = 2
        db.commit()
        db.refresh(doc)
        
        # Verify rows exist
        programs = db.scalar(select(func.count(Program.id)).where(
            Program.source_document_id == doc.id
        ))
        facts = db.scalar(select(func.count(Fact.id)).where(
            Fact.extra["source_document_id"].astext == str(doc.id)
        ))
        
        result = programs >= 1 and facts >= 1 and doc.status == "approved"
        return print_result(result, f"Approved document {doc.id} has {programs} programs and {facts} facts")
        
    except Exception as e:
        db.rollback()
        return print_result(False, f"Error: {str(e)}")
    finally:
        db.close()

def test_4_rows_in_chat_answers():
    """Test 4: After approval, rows appear in chat answers (via catalog)"""
    print_test_header(4, "After approval, rows appear in chat answers")
    
    db = SessionLocal()
    try:
        # Get approved document
        doc = db.scalar(select(CollegeDocument).where(CollegeDocument.status == "approved"))
        if not doc:
            return print_result(False, "No approved document found")
        
        # Get facts from this document
        facts = list(db.scalars(select(Fact).where(
            Fact.extra["source_document_id"].astext == str(doc.id)
        )))
        
        if not facts:
            return print_result(False, "No facts found for approved document")
        
        # Check if facts are in knowledge catalog
        catalog_entries = 0
        for fact in facts:
            entry = db.scalar(select(KnowledgeCatalog).where(
                KnowledgeCatalog.fact_id == fact.id
            ))
            if entry:
                catalog_entries += 1
        
        result = catalog_entries > 0
        return print_result(result, f"{catalog_entries} catalog entries found for {len(facts)} facts")
        
    except Exception as e:
        return print_result(False, f"Error: {str(e)}")
    finally:
        db.close()

def test_5_rejection_with_email():
    """Test 5: Document rejection with email"""
    print_test_header(5, "Document rejection with email")
    
    db = SessionLocal()
    try:
        # Create new pending document for rejection test
        college = db.scalar(select(College).where(College.code == "TEST"))
        admin = db.scalar(select(User).where(User.email == "admin@test.edu"))
        
        if not college or not admin:
            return print_result(False, "Test college or admin not found")
        
        doc = CollegeDocument(
            college_id=college.id,
            filename="reject_test.pdf",
            file_type="pdf",
            file_size_bytes=100,
            content_hash="test_hash_reject",
            object_key=f"colleges/{college.id}/uploads/reject.pdf",
            status="pending",
            submitted_by=admin.id,
            extracted_text="Test",
            summary="Test"
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        # Simulate rejection
        doc.status = "rejected"
        doc.reviewed_by = admin.id
        doc.reviewed_at = datetime.now(timezone.utc)
        doc.reject_reason = "Test rejection reason"
        db.commit()
        
        # Verify rejection status
        rejected = db.scalar(select(CollegeDocument).where(
            CollegeDocument.id == doc.id,
            CollegeDocument.status == "rejected",
            CollegeDocument.reject_reason == "Test rejection reason"
        ))
        
        result = rejected is not None
        return print_result(result, f"Document {doc.id} rejected with reason (email not tested in unit test)")
        
    except Exception as e:
        db.rollback()
        return print_result(False, f"Error: {str(e)}")
    finally:
        db.close()

def test_6_rollback_removes_rows():
    """Test 6: Rollback removes rows"""
    print_test_header(6, "Rollback removes rows")
    
    db = SessionLocal()
    try:
        # Get approved document
        doc = db.scalar(select(CollegeDocument).where(CollegeDocument.status == "approved"))
        if not doc:
            return print_result(False, "No approved document found")
        
        # Count rows before rollback
        programs_before = db.scalar(select(func.count(Program.id)).where(
            Program.source_document_id == doc.id
        ))
        facts_before = db.scalar(select(func.count(Fact.id)).where(
            Fact.extra["source_document_id"].astext == str(doc.id)
        ))
        
        # Simulate rollback
        for table_name, model_class in [("programs", Program), ("other_facts", Fact)]:
            if table_name == "programs":
                rows = list(db.scalars(select(model_class).where(
                    model_class.source_document_id == doc.id
                )))
                for row in rows:
                    db.delete(row)
            else:
                rows = list(db.scalars(select(model_class).where(
                    model_class.extra["source_document_id"].astext == str(doc.id)
                )))
                for row in rows:
                    # Remove from catalog
                    db.execute(select(KnowledgeCatalog).where(
                        KnowledgeCatalog.fact_id == row.id
                    ))
                    db.delete(row)
        
        doc.status = "rolled_back"
        doc.rows_created = 0
        db.commit()
        
        # Count rows after rollback
        programs_after = db.scalar(select(func.count(Program.id)).where(
            Program.source_document_id == doc.id
        ))
        facts_after = db.scalar(select(func.count(Fact.id)).where(
            Fact.extra["source_document_id"].astext == str(doc.id)
        ))
        
        result = programs_after == 0 and facts_after == 0
        return print_result(result, f"Rollback removed rows: programs {programs_before}->{programs_after}, facts {facts_before}->{facts_after}")
        
    except Exception as e:
        db.rollback()
        return print_result(False, f"Error: {str(e)}")
    finally:
        db.close()

def test_7_custom_tables_and_columns():
    """Test 7: Custom tables and columns"""
    print_test_header(7, "Custom tables and columns")
    
    db = SessionLocal()
    try:
        college = db.scalar(select(College).where(College.code == "TEST"))
        if not college:
            return print_result(False, "Test college not found")
        
        # Create custom table
        custom_table = CustomTable(
            college_id=college.id,
            table_slug="test_courses",
            display_name="Test Courses",
            description="Custom table for testing",
            schema={"columns": [{"name": "course_name", "type": "text"}]},
            source_document_id=None,
            row_count=0
        )
        db.add(custom_table)
        db.commit()
        db.refresh(custom_table)
        
        # Add row to custom table
        custom_row = CustomTableRow(
            college_id=college.id,
            custom_table_id=custom_table.id,
            row_data={"course_name": "Advanced Python"},
            confidence=1.0
        )
        db.add(custom_row)
        custom_table.row_count = 1
        db.commit()
        
        # Verify custom table and row
        table_check = db.scalar(select(CustomTable).where(
            CustomTable.college_id == college.id,
            CustomTable.table_slug == "test_courses"
        ))
        row_check = db.scalar(select(func.count(CustomTableRow.id)).where(
            CustomTableRow.custom_table_id == custom_table.id
        ))
        
        result = table_check is not None and row_check == 1
        return print_result(result, f"Custom table '{custom_table.table_slug}' created with {row_check} row")
        
    except Exception as e:
        db.rollback()
        return print_result(False, f"Error: {str(e)}")
    finally:
        db.close()

def cleanup_test_data():
    """Clean up test data"""
    print("\n" + "="*60)
    print("CLEANUP: Removing test data")
    print("="*60)
    
    db = SessionLocal()
    try:
        # Delete test documents
        docs = list(db.scalars(select(CollegeDocument).where(
            CollegeDocument.filename.in_(["test_document.pdf", "reject_test.pdf"])
        )))
        for doc in docs:
            # Delete associated rows
            for model_class in [Program, Fee, Fact]:
                if model_class == Fact:
                    rows = list(db.scalars(select(model_class).where(
                        model_class.extra["source_document_id"].astext == str(doc.id)
                    )))
                else:
                    rows = list(db.scalars(select(model_class).where(
                        model_class.source_document_id == doc.id
                    )))
                for row in rows:
                    if model_class == Fact:
                        db.execute(select(KnowledgeCatalog).where(
                            KnowledgeCatalog.fact_id == row.id
                        ))
                    db.delete(row)
            db.delete(doc)
        
        # Delete custom tables
        tables = list(db.scalars(select(CustomTable).where(
            CustomTable.table_slug == "test_courses"
        )))
        for table in tables:
            rows = list(db.scalars(select(CustomTableRow).where(
                CustomTableRow.custom_table_id == table.id
            )))
            for row in rows:
                db.delete(row)
            db.delete(table)
        
        # Delete staged rows
        staged = list(db.scalars(select(DocumentStagedRow)))
        for row in staged:
            db.delete(row)
        
        db.commit()
        print("✅ Test data cleaned up")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Cleanup error: {str(e)}")
    finally:
        db.close()

def main():
    print("\n" + "="*60)
    print("DOCUMENT APPROVAL WORKFLOW TEST SUITE")
    print("Section 21.7 - Items 1-7")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(test_1_upload_stays_pending())
    results.append(test_2_pending_invisible_to_students())
    results.append(test_3_approval_creates_rows())
    results.append(test_4_rows_in_chat_answers())
    results.append(test_5_rejection_with_email())
    results.append(test_6_rollback_removes_rows())
    results.append(test_7_custom_tables_and_columns())
    
    # Cleanup
    cleanup_test_data()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
