"""Build structured data tables from extracted data with proper parsing"""
import re
from sqlalchemy import select
from .db import SessionLocal
from .models import (
    College, Page, ExtractedTable, PageSection, StructuredData, Fact,
    Program, Fee, Faculty, Department, Facility, Hostel, Placement, Scholarship, Event
)


def build_structured_data(college_id: int, job_id: int):
    """Build structured data from extracted tables, sections, and structured data"""
    db = SessionLocal()
    try:
        pages = db.scalars(select(Page).where(Page.college_id == college_id, Page.job_id == job_id)).all()
        for page in pages:
            tables = db.scalars(select(ExtractedTable).where(ExtractedTable.page_id == page.id)).all()
            for table in tables:
                build_from_table(db, college_id, page.id, table)
            sections = db.scalars(select(PageSection).where(PageSection.page_id == page.id)).all()
            build_from_sections(db, college_id, page.id, sections)
            structured_data_list = db.scalars(select(StructuredData).where(StructuredData.page_id == page.id)).all()
            build_from_jsonld(db, college_id, page.id, structured_data_list)
        db.commit()
    finally:
        db.close()


def parse_fee_amount(text):
    """Parse numeric fee amount from text"""
    # Match patterns like "Rs 50000", "50000", "50,000", "50k"
    patterns = [
        r'Rs\s*[\d,]+(?:\.\d+)?',
        r'[\d,]+(?:\.\d+)?\s*(?:Rs|INR)',
        r'[\d,]+(?:\.\d+)?',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group().replace(',', '').replace('Rs', '').replace('INR', '').strip()
            try:
                return float(amount_str)
            except ValueError:
                pass
    return None


def build_from_table(db, college_id: int, page_id: int, table: ExtractedTable):
    """Build structured data from HTML tables with better parsing"""
    headers = table.headers
    rows = table.rows
    header_text = " ".join(str(h).lower() for h in headers)
    
    # Programs table - look for "program", "course", "degree" in headers
    if any(kw in header_text for kw in ["program", "course", "degree", "bachelor", "master"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                # Only create if it looks like a program name (not a year or number)
                title = str(row[0]).strip()
                if len(title) > 5 and not re.match(r'^\d{4}-\d{2}$', title) and not title.replace(' ', '').isdigit():
                    existing = db.scalar(select(Program).where(Program.college_id == college_id, Program.source_page_id == page_id, Program.title == title[:300]))
                    if not existing:
                        db.add(Program(college_id=college_id, source_page_id=page_id, title=title[:300], data=data, confidence=0.7, source_sections=['table']))
                        db.flush()
    
    # Fees table - look for "fee", "tuition", "amount", "price" and numeric values
    elif any(kw in header_text for kw in ["fee", "tuition", "cost", "amount", "price"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                row_text = " ".join(str(v) for v in row)
                amount = parse_fee_amount(row_text)
                if amount:
                    title = str(row[0]).strip()[:300]
                    existing = db.scalar(select(Fee).where(Fee.college_id == college_id, Fee.source_page_id == page_id, Fee.title == title))
                    if not existing:
                        db.add(Fee(college_id=college_id, source_page_id=page_id, title=title, data=data, amount=amount, confidence=0.8, source_sections=['table']))
                        db.flush()
    
    # Faculty table
    elif any(kw in header_text for kw in ["faculty", "professor", "staff", "teacher"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                title = str(row[0]).strip()[:300]
                if len(title) > 3:
                    existing = db.scalar(select(Faculty).where(Faculty.college_id == college_id, Faculty.source_page_id == page_id, Faculty.title == title))
                    if not existing:
                        db.add(Faculty(college_id=college_id, source_page_id=page_id, title=title, data=data, confidence=0.7, source_sections=['table']))
                        db.flush()
    
    # Department table
    elif any(kw in header_text for kw in ["department", "school", "division"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                title = str(row[0]).strip()[:300]
                if len(title) > 3:
                    existing = db.scalar(select(Department).where(Department.college_id == college_id, Department.source_page_id == page_id, Department.title == title))
                    if not existing:
                        db.add(Department(college_id=college_id, source_page_id=page_id, title=title, data=data, confidence=0.7, source_sections=['table']))
                        db.flush()
    
    # Facilities table
    elif any(kw in header_text for kw in ["facility", "infrastructure", "lab", "library", "room"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                title = str(row[0]).strip()[:300]
                if len(title) > 3:
                    existing = db.scalar(select(Facility).where(Facility.college_id == college_id, Facility.source_page_id == page_id, Facility.title == title))
                    if not existing:
                        db.add(Facility(college_id=college_id, source_page_id=page_id, title=title, data=data, confidence=0.7, source_sections=['table']))
                        db.flush()
    
    # Hostel table
    elif any(kw in header_text for kw in ["hostel", "dorm", "accommodation", "room"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                title = str(row[0]).strip()[:300]
                if len(title) > 3:
                    existing = db.scalar(select(Hostel).where(Hostel.college_id == college_id, Hostel.source_page_id == page_id, Hostel.title == title))
                    if not existing:
                        db.add(Hostel(college_id=college_id, source_page_id=page_id, title=title, data=data, confidence=0.7, source_sections=['table']))
                        db.flush()
    
    # Placements table - but don't misclassify years as programs
    elif any(kw in header_text for kw in ["placement", "salary", "package", "company", "recruit"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                title = str(row[0]).strip()[:300]
                # Skip years like "2023-24"
                if not re.match(r'^\d{4}-\d{2}$', title) and len(title) > 3:
                    existing = db.scalar(select(Placement).where(Placement.college_id == college_id, Placement.source_page_id == page_id, Placement.title == title))
                    if not existing:
                        db.add(Placement(college_id=college_id, source_page_id=page_id, title=title, data=data, confidence=0.7, source_sections=['table']))
                        db.flush()
    
    # Scholarships table
    elif any(kw in header_text for kw in ["scholarship", "grant", "aid", "financial"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                title = str(row[0]).strip()[:300]
                if len(title) > 3:
                    existing = db.scalar(select(Scholarship).where(Scholarship.college_id == college_id, Scholarship.source_page_id == page_id, Scholarship.title == title))
                    if not existing:
                        db.add(Scholarship(college_id=college_id, source_page_id=page_id, title=title, data=data, confidence=0.7, source_sections=['table']))
                        db.flush()
    
    # Events table
    elif any(kw in header_text for kw in ["event", "schedule", "calendar", "date"]):
        for row in rows:
            if len(row) > 0:
                data = dict(zip(headers, row))
                title = str(row[0]).strip()[:300]
                if len(title) > 3:
                    existing = db.scalar(select(Event).where(Event.college_id == college_id, Event.source_page_id == page_id, Event.title == title))
                    if not existing:
                        db.add(Event(college_id=college_id, source_page_id=page_id, title=title, data=data, confidence=0.7, source_sections=['table']))
                        db.flush()
    else:
        # Unknown table - store in other_facts
        for row in rows:
            if len(row) > 0:
                value = " | ".join(str(v) for v in row)
                title = str(row[0]).strip()[:300]
                existing = db.scalar(select(Fact).where(Fact.college_id == college_id, Fact.source_page_id == page_id, Fact.title == title, Fact.category == "website table"))
                if not existing:
                    db.add(Fact(college_id=college_id, category="website table", title=title, value=value[:50000], source_page_id=page_id, confidence=0.5, source_sections=['table']))
                    db.flush()


def build_from_sections(db, college_id: int, page_id: int, sections):
    """Build structured data from page sections - only high-confidence matches"""
    for section in sections:
        text = section.section_text or ""
        heading = section.heading_text.lower()
        
        # Only create structured data if the section content is substantial
        if len(text) < 50:
            continue
        
        # Programs - require specific patterns
        if any(kw in heading for kw in ["program", "course", "degree"]):
            # Skip breadcrumb-like headings
            if "home /" in text.lower() or "/" in heading:
                continue
            title = section.heading_text[:300]
            existing = db.scalar(select(Program).where(Program.college_id == college_id, Program.source_page_id == page_id, Program.title == title))
            if not existing:
                db.add(Program(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, confidence=0.5, source_sections=['section']))
                db.flush()
        
        # Fees - require numeric amounts
        elif any(kw in heading for kw in ["fee", "tuition", "cost"]):
            amount = parse_fee_amount(text)
            if amount:
                title = section.heading_text[:300]
                existing = db.scalar(select(Fee).where(Fee.college_id == college_id, Fee.source_page_id == page_id, Fee.title == title))
                if not existing:
                    db.add(Fee(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, amount=amount, confidence=0.6, source_sections=['section']))
                    db.flush()
        
        # Faculty
        elif any(kw in heading for kw in ["faculty", "professor"]):
            title = section.heading_text[:300]
            existing = db.scalar(select(Faculty).where(Faculty.college_id == college_id, Faculty.source_page_id == page_id, Faculty.title == title))
            if not existing:
                db.add(Faculty(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, confidence=0.5, source_sections=['section']))
                db.flush()
        
        # Departments
        elif any(kw in heading for kw in ["department", "school"]):
            title = section.heading_text[:300]
            existing = db.scalar(select(Department).where(Department.college_id == college_id, Department.source_page_id == page_id, Department.title == title))
            if not existing:
                db.add(Department(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, confidence=0.5, source_sections=['section']))
                db.flush()
        
        # Facilities
        elif any(kw in heading for kw in ["facility", "lab"]):
            title = section.heading_text[:300]
            existing = db.scalar(select(Facility).where(Facility.college_id == college_id, Facility.source_page_id == page_id, Facility.title == title))
            if not existing:
                db.add(Facility(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, confidence=0.5, source_sections=['section']))
                db.flush()
        
        # Hostel
        elif any(kw in heading for kw in ["hostel", "accommodation"]):
            title = section.heading_text[:300]
            existing = db.scalar(select(Hostel).where(Hostel.college_id == college_id, Hostel.source_page_id == page_id, Hostel.title == title))
            if not existing:
                db.add(Hostel(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, confidence=0.5, source_sections=['section']))
                db.flush()
        
        # Placements
        elif any(kw in heading for kw in ["placement", "recruitment"]):
            title = section.heading_text[:300]
            existing = db.scalar(select(Placement).where(Placement.college_id == college_id, Placement.source_page_id == page_id, Placement.title == title))
            if not existing:
                db.add(Placement(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, confidence=0.5, source_sections=['section']))
                db.flush()
        
        # Scholarships
        elif any(kw in heading for kw in ["scholarship", "financial aid"]):
            title = section.heading_text[:300]
            existing = db.scalar(select(Scholarship).where(Scholarship.college_id == college_id, Scholarship.source_page_id == page_id, Scholarship.title == title))
            if not existing:
                db.add(Scholarship(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, confidence=0.5, source_sections=['section']))
                db.flush()
        
        # Events
        elif any(kw in heading for kw in ["event", "calendar"]):
            title = section.heading_text[:300]
            existing = db.scalar(select(Event).where(Event.college_id == college_id, Event.source_page_id == page_id, Event.title == title))
            if not existing:
                db.add(Event(college_id=college_id, source_page_id=page_id, title=title, data={"text": text}, confidence=0.5, source_sections=['section']))
                db.flush()


def build_from_jsonld(db, college_id: int, page_id: int, structured_data_list):
    """Build structured data from JSON-LD - high confidence"""
    for sd in structured_data_list:
        if sd.format == "json-ld" and sd.schema_type:
            data = sd.data
            if isinstance(data, dict):
                schema_type = sd.schema_type.lower()
                if schema_type == "course" or schema_type == "courseinstance":
                    name = str(data.get("name", ""))[:300]
                    if name:
                        existing = db.scalar(select(Program).where(Program.college_id == college_id, Program.source_page_id == page_id, Program.title == name))
                        if not existing:
                            db.add(Program(college_id=college_id, source_page_id=page_id, title=name, data=data, confidence=0.9, source_sections=['json-ld']))
                            db.flush()
                elif schema_type == "person" or schema_type == "faculty":
                    name = str(data.get("name", ""))[:300]
                    if name:
                        existing = db.scalar(select(Faculty).where(Faculty.college_id == college_id, Faculty.source_page_id == page_id, Faculty.title == name))
                        if not existing:
                            db.add(Faculty(college_id=college_id, source_page_id=page_id, title=name, data=data, confidence=0.9, source_sections=['json-ld']))
                            db.flush()
                elif schema_type == "event":
                    name = str(data.get("name", ""))[:300]
                    if name:
                        existing = db.scalar(select(Event).where(Event.college_id == college_id, Event.source_page_id == page_id, Event.title == name))
                        if not existing:
                            db.add(Event(college_id=college_id, source_page_id=page_id, title=name, data=data, confidence=0.9, source_sections=['json-ld']))
                            db.flush()
