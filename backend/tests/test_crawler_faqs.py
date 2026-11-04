from bs4 import BeautifulSoup

from app.crawler import extract_faqs


def test_extract_faqs_from_class_based_accordions():
    soup = BeautifulSoup(
        '<div class="accordion"><span class="question">What is BCA?</span>'
        '<div class="answer">A three-year program.</div></div>'
        '<section class="faq-item"><h3>Where is the campus?</h3>'
        '<div class="content">Ahmedabad.</div></section>',
        "html.parser",
    )
    assert extract_faqs(soup, "https://college.example/faq") == [
        {"question": "What is BCA?", "answer": "A three-year program."},
        {"question": "Where is the campus?", "answer": "Ahmedabad."},
    ]
