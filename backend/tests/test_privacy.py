from app.privacy import mask_personal_data


def test_mask_personal_data_removes_email_and_phone():
    value = mask_personal_data("Please call +91 98765 43210 or email student@example.edu")
    assert "98765 43210" not in value
    assert "student@example.edu" not in value
    assert "[phone]" in value
    assert "[email]" in value


def test_mask_personal_data_leaves_ordinary_question_intact():
    assert mask_personal_data("What are the admission requirements for session 2026 2027?") == (
        "What are the admission requirements for session 2026 2027?"
    )
