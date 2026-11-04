from bs4 import BeautifulSoup

from app.crawler import extract_html_structured_facts, extract_html_tables, strip_hidden_content


def test_extract_html_table_preserves_headers_and_row_values():
    soup = BeautifulSoup(
        """<table><caption>Programs</caption><thead><tr><th>Program</th><th>Fee</th></tr></thead>
        <tbody><tr><td>BCA</td><td>₹1,20,000</td></tr></tbody></table>""",
        "html.parser",
    )
    facts = extract_html_tables(soup, "Admissions")
    assert facts == [{
        "category": "website table 1: Programs",
        "title": "BCA",
        "value": "Program: BCA | Fee: ₹1,20,000",
    }]


def test_extract_html_tables_disambiguates_duplicate_row_labels():
    soup = BeautifulSoup(
        "<table><tr><th>Event</th><th>Date</th></tr><tr><td>Orientation</td><td>1 Aug</td></tr><tr><td>Orientation</td><td>2 Aug</td></tr></table>",
        "html.parser",
    )
    facts = extract_html_tables(soup, "Calendar")
    assert [fact["title"] for fact in facts] == ["Orientation", "Orientation · row 2"]
    assert facts[1]["value"].endswith("Date: 2 Aug")


def test_strip_hidden_content_removes_invisible_markup_before_indexing():
    soup = BeautifulSoup(
        """<main><p>Visible evidence</p><div hidden>hidden attribute</div>
        <p aria-hidden="true">aria hidden</p><span style="display: none">css hidden</span>
        <div class="sr-only">screen-reader helper</div><script>script text</script></main>""",
        "html.parser",
    )
    strip_hidden_content(soup)
    text = soup.get_text(" ", strip=True)
    assert text == "Visible evidence"


def test_extract_html_definition_list_uses_page_labels():
    soup = BeautifulSoup(
        "<dl><dt>Eligibility</dt><dd>Undergraduate qualification</dd><dt>Duration</dt><dd>Three years</dd></dl>",
        "html.parser",
    )
    facts = extract_html_structured_facts(soup, "Program details")
    assert facts == [
        {"category": "website definition list 1: Program details", "title": "Eligibility", "value": "Undergraduate qualification"},
        {"category": "website definition list 1: Program details", "title": "Duration", "value": "Three years"},
    ]
