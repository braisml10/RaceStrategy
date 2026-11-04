"""Pruebas de la API con un CSV sintético en una carpeta temporal."""

import pytest
from fastapi.testclient import TestClient

import api
from helpers import SESSION_ROWS, write_session


@pytest.fixture()
def client(tmp_path, monkeypatch):
    write_session(tmp_path / "FP1.csv", SESSION_ROWS)
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    api._load.cache_clear()
    api._marked.cache_clear()
    return TestClient(api.app)


def test_sessions_and_settings(client):
    body = client.get("/api/sessions").json()
    assert body["sessions"] == [{"id": "FP1.csv", "name": "FP1"}]
    assert body["settings"] == {"msSeparator": ".", "slowThresholdPct": 107}


def test_overview(client):
    body = client.get("/api/sessions/FP1.csv/overview").json()
    assert (body["laps"], body["cars"], body["drivers"]) == (12, 3, 4)
    assert [c["id"] for c in body["categories"]] == ["HYPERCAR", "LMGT3"]
    hyper = body["categories"][0]
    assert hyper["label"] == "Hypercar" and hyper["cars"] == 2
    assert hyper["bestLap"]["text"] == "01:33.000" and hyper["bestLap"]["car"] == "7"
    assert body["clockStart"] == "11:32:00"


def test_category(client):
    body = client.get("/api/sessions/FP1.csv/categories/HYPERCAR").json()
    assert body["counts"] == {"laps": 10, "paceLaps": 4, "cars": 2, "drivers": 3}
    assert [b["key"] for b in body["bests"]] == ["lap", "s1", "s2", "s3"]
    lap = body["bests"][0]
    assert (lap["car"], lap["driver"], lap["lap"], lap["clock"]) == ("7", "Carl C", 2, "11:33:33")
    ranking = body["rankings"]["lap"]
    assert [r["car"] for r in ranking] == ["7", "007"]
    assert ranking[0]["gapText"] == "—" and ranking[1]["gapText"] == "+1.000"
    assert set(body["rankings"]) == {"lap", "s1", "s2", "s3"}
    assert [c["car"] for c in body["topCars"]] == ["7", "007"]
    only_pace = [p["lap"] for p in body["topCars"][1]["laps"]]
    assert only_pace == [2, 3, 6]                       # solo vueltas de ritmo
    assert [c["number"] for c in body["cars"]] == ["007", "7"]


def test_slow_threshold_changes_pace_laps(client):
    strict = client.get("/api/sessions/FP1.csv/categories/HYPERCAR?slow=100").json()
    relaxed = client.get("/api/sessions/FP1.csv/categories/HYPERCAR?slow=115").json()
    assert relaxed["counts"]["paceLaps"] > strict["counts"]["paceLaps"]


def test_car(client):
    body = client.get("/api/sessions/FP1.csv/cars/007").json()
    assert body["car"] == {"number": "007", "team": "Aston", "manufacturer": "", "category": "HYPERCAR"}
    assert body["counts"] == {"laps": 8, "paceLaps": 3}
    ana, ben = body["drivers"]
    assert ana["name"] == "Ana A" and ana["best"]["text"] == "01:34.000"
    assert ana["deltaText"] == "Referencia" and ben["deltaText"] == "+0.500 s"
    assert ana["s1"]["text"] == "00:29.500"
    assert len(body["laps"]) == 8
    lap5 = body["laps"][4]
    assert lap5["status"] == "Salida de boxes" and not lap5["isPace"] and lap5["text"] == "03:00.000"


def test_errors(client):
    assert client.get("/api/sessions/nope.csv/overview").status_code == 404
    assert client.get("/api/sessions/..%2Fsecret.csv/overview").status_code == 404
    assert client.get("/api/sessions/FP1.csv/categories/LMP2").status_code == 404
    assert client.get("/api/sessions/FP1.csv/cars/999").status_code == 404
    assert client.get("/api/sessions/FP1.csv/categories/HYPERCAR?slow=50").status_code == 422


def test_cors_allows_the_vite_origin(client):
    reply = client.get("/api/sessions", headers={"Origin": "http://localhost:5173"})
    assert reply.headers["access-control-allow-origin"] == "http://localhost:5173"