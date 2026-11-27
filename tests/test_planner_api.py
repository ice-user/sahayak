"""POST /api/plan and GET /api/schemes/{id}/apply."""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from sahayak import planner
from sahayak.agent import Agent
from sahayak.tools import Toolbox
from server.config import Settings
from server.main import create_app

FIX = Path(__file__).parent / "fixtures"


def make_client(**settings):
    app = create_app(lambda tb: Agent(client=NS(), model="fake", toolbox=tb), Toolbox(search_mode="bm25"),
                     Settings(**settings))
    return TestClient(app)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(planner, "APPLICATIONS_PATH", FIX / "applications_sample.json")
    monkeypatch.setattr(planner, "DOCUMENTS_PATH", FIX / "documents_sample.json")
    with make_client() as tc:
        yield tc


def test_plan_returns_plan(client):
    r = client.post("/api/plan", json={"scheme_ids": ["pm_kisan", "pmuy"], "lang": "hi",
                                       "profile": {"income_tax_payer_last_year": True}})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["schemes"] == 2 and body["summary"]["trips"] == 1
    assert body["watch_outs"][0]["personal"] is True
    assert body["checklist"][0]["name"] == "आधार कार्ड"
    assert body["enrol_groups"][0]["scheme_ids"] == ["pm_kisan", "pmuy"]
    assert len(body["where_to_go"]) == 2
    assert r.headers["x-content-type-options"] == "nosniff"


def test_plan_without_profile_and_default_lang(client):
    body = client.post("/api/plan", json={"scheme_ids": ["ssy"]}).json()
    assert body["lang"] == "en" and body["steps"][0]["group"] == "Post office"


@pytest.mark.parametrize("body", [
    {}, {"scheme_ids": []}, {"scheme_ids": [f"s{i}" for i in range(11)]}, {"scheme_ids": ["x" * 65]},
    {"scheme_ids": ["ssy"], "lang": "fr"}, {"scheme_ids": ["ssy"], "profile": {"age": -5}},
    {"scheme_ids": ["ssy"], "profile": {"income": 5}}, {"scheme_ids": "ssy"},
])
def test_plan_validation_400(client, body):
    r = client.post("/api/plan", json=body)
    assert r.status_code == 400 and "detail" in r.json()


def test_plan_with_missing_data_files_is_empty_not_500(client, monkeypatch):
    monkeypatch.setattr(planner, "APPLICATIONS_PATH", FIX / "nope.json")
    r = client.post("/api/plan", json={"scheme_ids": ["pm_kisan", "ghost"]})
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["data_available"] is False and s["missing_application_data"] == ["pm_kisan"] and s["unknown_schemes"] == ["ghost"]


def test_plan_rate_limited(monkeypatch):
    monkeypatch.setattr(planner, "APPLICATIONS_PATH", FIX / "applications_sample.json")
    with make_client(rate_limit_per_10min=1) as tc:
        codes = [tc.post("/api/plan", json={"scheme_ids": ["ssy"]}).status_code for _ in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429


def test_apply_record_and_404(client):
    r = client.get("/api/schemes/ssy/apply")
    assert r.status_code == 200 and r.json()["office"] == "Post office"
    r = client.get("/api/schemes/ignoaps/apply")
    assert r.status_code == 404 and "detail" in r.json()
    assert client.get("/api/schemes/ssy").status_code == 200  # existing route unaffected
