import pytest
from fastapi.testclient import TestClient

from dataMasking import mask_personal_data
from dataMasking.api import MAX_TEXT_LENGTH, create_app

from .cases import KEPT, MASKED, Case


@pytest.mark.parametrize("case", MASKED, ids=lambda c: c.id)
def test_masks_personal_data(case: Case) -> None:
    assert mask_personal_data(case.text).text == case.expected


@pytest.mark.parametrize("case", KEPT, ids=lambda c: c.id)
def test_keeps_names_and_facts(case: Case) -> None:
    result = mask_personal_data(case.text)
    assert result.text == case.expected
    assert not result.changed


def test_entities_point_at_original_values() -> None:
    text = "Jan Kowalski, tel. 600 100 200, PESEL 44051401359"
    result = mask_personal_data(text)
    assert [(e.label, e.placeholder, text[e.start : e.end]) for e in result.entities] == [
        ("TELEFON", "[TELEFON_1]", "600 100 200"),
        ("PESEL", "[PESEL_1]", "44051401359"),
    ]
    assert result.counts == {"TELEFON": 1, "PESEL": 1}


def test_same_value_gets_same_placeholder_across_formats() -> None:
    result = mask_personal_data("+48 22 123 45 67 i (22) 123-45-67 oraz 601 222 333")
    assert result.text == "[TELEFON_1] i [TELEFON_1] oraz [TELEFON_2]"


def test_empty_text() -> None:
    assert mask_personal_data("").text == ""


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_api_returns_masked_text_without_echoing_values(client: TestClient) -> None:
    response = client.post("/api/masking", json={"text": "Anna Nowak, anna@nowak.pl"})
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "masked_text": "Anna Nowak, [EMAIL_1]",
        "entities": [{"label": "EMAIL", "placeholder": "[EMAIL_1]", "start": 12, "end": 25}],
        "counts": {"EMAIL": 1},
    }
    assert "anna@nowak.pl" not in response.text


def test_api_rejects_too_long_text(client: TestClient) -> None:
    response = client.post("/api/masking", json={"text": "x" * (MAX_TEXT_LENGTH + 1)})
    assert response.status_code == 422


def test_api_health(client: TestClient) -> None:
    assert client.get("/api/masking/health").json() == {"status": "ok"}
