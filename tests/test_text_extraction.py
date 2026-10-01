import json

import pytest

from docintel.text_extraction import UnsupportedDocumentError, extract_text, normalize_text


def test_plain_text_is_normalized():
    raw = b"Invoice\r\n\r\n\r\n\r\nTotal: 1.00   \r\n"
    assert extract_text(raw, "a.txt") == "Invoice\n\nTotal: 1.00"


def test_ocr_json_pages_are_ordered():
    ocr = {"pages": [{"page": 2, "lines": ["second"]}, {"page": 1, "lines": ["first"]}]}
    assert extract_text(json.dumps(ocr).encode(), "x.json") == "first\n\nsecond"


def test_unsupported_extension():
    with pytest.raises(UnsupportedDocumentError):
        extract_text(b"\x89PNG", "scan.png")


def test_bad_ocr_json():
    with pytest.raises(UnsupportedDocumentError):
        extract_text(b'{"foo": 1}', "x.json")


def test_unicode_normalization():
    assert normalize_text("ﬁle\u00a0name") == "file name"
