import pytest

from main import extract_chunk_items, extract_json_block_from_content


def test_extract_chunk_items_supports_known_text_fields():
    chunks = [
        {"name": "intro", "content": " first "},
        {"fileName": "chapter", "text": " second "},
        {"title": "ignored-title", "chunk": " third "},
    ]

    items = extract_chunk_items(chunks, [0, 1, 2, 99, -1])

    assert items == [
        {"index": 0, "title": "intro", "text": "first"},
        {"index": 1, "title": "chapter", "text": "second"},
        {"index": 2, "title": "chunk-2", "text": "third"},
    ]


def test_extract_json_block_from_content_handles_wrapped_json():
    content = 'prefix text {"ga_pairs": [{"id": "q1", "question": "What?"}]} suffix text'

    data = extract_json_block_from_content(content)

    assert data["ga_pairs"][0]["id"] == "q1"


def test_extract_json_block_from_content_rejects_missing_ga_pairs():
    with pytest.raises(ValueError, match="ga_pairs"):
        extract_json_block_from_content('{"items": []}')
