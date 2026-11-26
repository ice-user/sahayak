import pytest

from sahayak.lang import MAX_STEPS_MESSAGES, detect_language, detect_session_language, has_letters
from sahayak.privacy import mask_pii


def test_language_detection_lives_in_sahayak_and_server_reuses_it():
    from server import suggestions
    assert suggestions.detect_language is detect_language and suggestions.has_letters is has_letters
    assert detect_language("मेरी उम्र 60 है") == "hi" and detect_language("என் வயது") == "ta"
    assert detect_language("meri umar 60 saal hai") == "hinglish" and detect_language("my age is 60") == "en"


def test_session_language_only_upgrades():
    msgs = [{"role": "user", "content": "meri maa 62 saal ki hain"}, {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "female"}, {"role": "user", "content": "62"}]
    assert detect_session_language(msgs) == "hinglish"
    assert detect_session_language([{"role": "user", "content": "hello"}]) == "en"
    assert detect_session_language([{"role": "system", "content": "मेरी"}]) == "en"


def test_every_language_has_a_max_steps_message():
    assert set(MAX_STEPS_MESSAGES) == {"en", "hi", "hinglish", "ta"}


@pytest.mark.parametrize("text, masked", [
    ("my aadhaar is 1234 5678 9012 ok", True),
    ("aadhaar 123456789012", True),
    ("aadhaar 1234-5678-9012", True),
    ("PAN ABCDE1234F please", True),
    ("pan abcde1234f", True),
    ("call 9876543210", True),
    ("call +91 98765 43210", True),
    ("call +91-9876543210", True),
    ("call 09876543210", True),
    ("I am 62 and earn 120000 a year", False),
    ("income 1000000000 and age 70", False),
    ("pension 12000 per month, 3 children aged 4 and 9", False),
    ("my account has 5000000 rupees", False),
])
def test_mask_pii(text, masked):
    out = mask_pii(text)
    assert ("[number removed]" in out) is masked
    if masked:
        assert not any(ch.isdigit() for ch in out)
    else:
        assert out == text


def test_mask_keeps_surrounding_text():
    assert mask_pii("age 62, phone 9876543210, widow") == "age 62, phone [number removed], widow"
