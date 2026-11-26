from __future__ import annotations

import pytest

from app.guardrails.pii import redact, redact_with_mapping, restore

# (text, raw PII values that must not survive, expected tags)
FIXTURES = [
    ("NIC 901234567V", ["901234567V"], ["[NIC]"]),
    ("new nic 199012345678.", ["199012345678"], ["[NIC]"]),
    ("lower x: 851234567x", ["851234567x"], ["[NIC]"]),
    ("passport N1234567 issued", ["N1234567"], ["[PASSPORT]"]),
    ("passport no: KX1234567", ["KX1234567"], ["[PASSPORT]"]),
    ("call +94 77 123 4567", ["77 123 4567"], ["[PHONE]"]),
    ("call +94771234567", ["+94771234567"], ["[PHONE]"]),
    ("mobile 0771234567 or 077-123-4567", ["0771234567", "077-123-4567"], ["[PHONE]"]),
    ("office 011 2345678", ["011 2345678"], ["[PHONE]"]),
    ("Kuwait +965 5123 4567", ["5123 4567"], ["[PHONE]"]),
    ("UAE 00971501234567", ["00971501234567"], ["[PHONE]"]),
    ("mail Worker.Name+1@example.co.uk", ["Worker.Name+1@example.co.uk"], ["[EMAIL]"]),
    ("Bank account no: 8001234567", ["8001234567"], ["[BANK_ACCOUNT]"]),
    ("deposit to A/C 1234 5678 9012", ["1234 5678 9012"], ["[BANK_ACCOUNT]"]),
    ("acc no 0012-3456-7890-12", ["0012-3456-7890-12"], ["[BANK_ACCOUNT]"]),
    ("BOC bank 87654321 Colombo", ["87654321"], ["[BANK_ACCOUNT]"]),
    # Sinhala around the values, including no space before the digits.
    ("මගේ ජා.හැ.අ. අංකය 901234567V යි", ["901234567V"], ["[NIC]"]),
    ("හැඳුනුම්පත අංකය199012345678", ["199012345678"], ["[NIC]"]),
    ("දුරකථන අංකය 0771234567 ට අමතන්න", ["0771234567"], ["[PHONE]"]),
    ("ගිණුම් අංකය 8001234567 ට මුදල් දමන්න", ["8001234567"], ["[BANK_ACCOUNT]"]),
    ("විද්‍යුත් තැපෑල worker@example.com", ["worker@example.com"], ["[EMAIL]"]),
    ("ගමන් බලපත්‍රය N7654321", ["N7654321"], ["[PASSPORT]"]),
    # Tamil around the values.
    ("என் தேசிய அடையாள அட்டை 851234567V", ["851234567V"], ["[NIC]"]),
    ("தொலைபேசி+94771234567க்கு அழைக்கவும்", ["+94771234567"], ["[PHONE]"]),
    ("வங்கி கணக்கு எண் 123456789012345", ["123456789012345"], ["[BANK_ACCOUNT]"]),
    ("மின்னஞ்சல் agent@mail.lk அனுப்பவும்", ["agent@mail.lk"], ["[EMAIL]"]),
    ("கடவுச்சீட்டு N1122334", ["N1122334"], ["[PASSPORT]"]),
]


@pytest.mark.parametrize(("text", "raw", "tags"), FIXTURES)
def test_every_pii_fixture_is_redacted(text, raw, tags):
    out = redact(text)
    for value in raw:
        assert value not in out
    for tag in tags:
        assert tag in out


@pytest.mark.parametrize(
    "text",
    [
        "verification 3f2b8c1e-1234-5678-9abc-123456789012",
        "id 12345678-1234-1234-1234-123456789012",
        "on 2026-11-24 at 10:15",
        "fee LKR 150000 and salary 1100 AED",
        "licence no 1234 valid until 2027-01-31",
        "page 2 of 4, clause 12.3",
        "model gemini-3.5-flash",
        "bank transfer of 450000 rupees",
    ],
)
def test_ids_dates_amounts_and_licences_are_kept(text):
    assert redact(text) == text


def test_surrounding_sinhala_and_tamil_text_is_preserved():
    assert redact("අංකය 0771234567 ට") == "අංකය [PHONE] ට"
    assert redact("கணக்கு 8001234567 இல்") == "கணக்கு [BANK_ACCOUNT] இல்"


def test_mapping_numbers_repeats_consistently_and_restores():
    text = "call 0771234567, then 0719876543, again 0771234567; nic 901234567V"
    redacted, mapping = redact_with_mapping(text)
    assert redacted == "call [PHONE_1], then [PHONE_2], again [PHONE_1]; nic [NIC_1]"
    assert mapping == {
        "[PHONE_1]": "0771234567",
        "[PHONE_2]": "0719876543",
        "[NIC_1]": "901234567V",
    }
    assert restore(redacted, mapping) == text


def test_restore_does_not_confuse_prefix_tags():
    mapping = {f"[PHONE_{i}]": f"07{i:08d}" for i in range(1, 12)}
    assert restore("[PHONE_1] [PHONE_11]", mapping) == "0700000001 0700000011"
