import json

import pytest
from pydantic import ValidationError

from app.mesh import parse_recommendation

PRODUCTS = [
    {"id": 14, "title": "Product Management Foundations"},
    {"id": 15, "title": "Advanced Product Strategy"},
]


def test_parse_recommendation_accepts_expected_shape():
    content = json.dumps({"title": "Product path", "narrative": "A focused path.", "items": [{"product_id": 14, "reason": "Build foundations."}]})

    payload = parse_recommendation(content, PRODUCTS)

    assert payload.title == "Product path"
    assert payload.items == [{"product_id": 14, "reason": "Build foundations."}]


def test_parse_recommendation_repairs_candidates_shape():
    content = json.dumps({"candidates": [{"title": "Product Management Foundations", "reason": "Matches product management."}]})

    payload = parse_recommendation(content, PRODUCTS)

    assert payload.title == "Courses selected for you"
    assert payload.items == [{"product_id": 14, "reason": "Matches product management."}]


def test_parse_recommendation_rejects_invented_candidates():
    content = json.dumps({"candidates": [{"title": "Invented Course", "reason": "Not in the catalogue."}]})

    with pytest.raises(ValidationError):
        parse_recommendation(content, PRODUCTS)
