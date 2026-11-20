"""Pruebas de la API con un CSV sintético en una carpeta temporal."""

import pytest
from fastapi.testclient import TestClient

import api
from helpers import SESSION_ROWS, STINT_CAR, car_rows, write_session


@pytest.fixture()
def client(tmp_path, monkeypatch):
    write_session(tmp_path / "FP1.csv", SESSION_ROWS)
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    api._load.cache_clear()
    api._marked.cache_clear()
    return TestClient(api.app)


def test_sessions_and_settings(client):
    body = client.get("/api/sessions").json()
    assert len(body["sessions"]) == 1      # con un solo archivo no hay "todas las sesiones"
    assert body["sessions"][0] | {"eventName": ""} == {
        "id": "FP1.csv", "name": "FP1", "overall": False, "event": ".", "eventName": "",
        "categories": ["HYPERCAR", "LMGT3"],
    }
    assert body["settings"] == {"msSeparator": ".", "slowThresholdPct": 107}


def test_sessions_list_their_categories(client, tmp_path):
    write_session(tmp_path / "GT3.csv", [SESSION_ROWS[10], SESSION_ROWS[11]])  # solo el #99 (LMGT3)
    (tmp_path / "BAD.csv").write_text("A;B\n1;2\n")                           # sin columna CLASS
    cats = {s["id"]: s["categories"] for s in client.get("/api/sessions").json()["sessions"]}
    assert cats == {
        "BAD.csv": None, "FP1.csv": ["HYPERCAR", "LMGT3"], "GT3.csv": ["LMGT3"],
        "__all__": None,                  # una sesión ilegible: no se sabe qué trae el conjunto
    }


def test_overview(client):
    body = client.get("/api/sessions/FP1.csv/overview").json()
    assert (body["laps"], body["cars"], body["drivers"]) == (12, 3, 4)
    assert [c["id"] for c in body["categories"]] == ["HYPERCAR", "LMGT3"]
    hyper = body["categories"][0]
    assert hyper["label"] == "Hypercar" and hyper["cars"] == 2
    assert hyper["bestLap"]["text"] == "01:33.000" and hyper["bestLap"]["car"] == "7"
    assert body["clockStart"] == "11:32:00"
    assert body["notices"] == []


def test_category(client):
    body = client.get("/api/sessions/FP1.csv/categories/HYPERCAR").json()
    assert body["counts"] == {"laps": 10, "paceLaps": 4, "cars": 2, "drivers": 3}
    assert [b["key"] for b in body["bests"]] == ["lap", "s1", "s2", "s3"]
    lap = body["bests"][0]
    assert (lap["car"], lap["driver"], lap["lap"], lap["clock"]) == ("7", "Carl C", 2, "11:33:33")
    assert lap["session"] == "FP1"
    ranking = body["rankings"]["lap"]
    assert [r["car"] for r in ranking] == ["7", "007"]
    assert ranking[0]["gapText"] == "—" and ranking[1]["gapText"] == "+1.000"
    assert set(body["rankings"]) == {"lap", "s1", "s2", "s3"}
    assert [c["car"] for c in body["pace"]] == ["7", "007"]       # todos los coches, más rápido primero
    only_pace = [p["lap"] for p in body["pace"][1]["laps"]]
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
    # misma mediana de ritmo (94.5) en los dos pilotos: ambos son referencia
    assert ana["medianGap"] == {"seconds": 0.0, "text": "Referencia"}
    assert ben["medianGap"] == {"seconds": 0.0, "text": "Referencia"}
    assert len(body["laps"]) == 8
    lap5 = body["laps"][4]
    assert lap5["status"] == "Salida de boxes" and not lap5["isPace"] and lap5["text"] == "03:00.000"
    assert [l["flag"] for l in body["laps"]] == ["", "", "", "", "", "", "FCY", ""]
    assert [l["pit"] for l in body["laps"]] == ["out", "", "", "in", "out", "", "", ""]


def test_car_stints_and_trend(client, tmp_path):
    body = client.get("/api/sessions/FP1.csv/cars/007").json()
    assert [(s["stint"], s["driver"], s["startLap"], s["endLap"]) for s in body["stints"]] == [
        (1, "Ana A", 1, 4), (2, "Ben B", 5, 8),
    ]
    assert all(s["trend"] is None for s in body["stints"])          # < 3 vueltas de ritmo
    assert [(l["lap"], l["stint"], l["stintLap"]) for l in body["laps"][3:6]] == [
        (4, 1, 4), (5, 2, 1), (6, 2, 2),
    ]

    # coche sintético con stints de pendiente conocida (0,1 / 0,2 / 0,1 s por vuelta)
    write_session(tmp_path / "STINT.csv", car_rows("5", STINT_CAR))
    stints = client.get("/api/sessions/STINT.csv/cars/5").json()["stints"]
    assert [s["trend"]["slope"] for s in stints] == pytest.approx([0.1, 0.2, 0.1])
    assert [s["trend"]["intercept"] for s in stints] == pytest.approx([94.8, 93.6, 93.8])
    assert [s["paceLaps"] for s in stints] == [4, 4, 3]
    assert stints[1]["median"]["text"] == "01:34.300"


def test_car_pit_stops(client, tmp_path):
    body = client.get("/api/sessions/FP1.csv/cars/007").json()
    [stop] = body["pitStops"]
    assert (stop["fromLap"], stop["toLap"]) == (4, 5)
    assert (stop["driverOut"], stop["driverIn"], stop["driverChange"]) == ("Ana A", "Ben B", True)
    assert stop["pit"]["seconds"] is not None
    assert body["drivers"][0]["mean"]["seconds"] == pytest.approx(94.5)

    write_session(tmp_path / "STINT.csv", car_rows("5", STINT_CAR))
    stops = client.get("/api/sessions/STINT.csv/cars/5").json()["pitStops"]
    assert [(s["fromLap"], s["toLap"]) for s in stops] == [(6, 7), (12, 13)]
    assert stops[0]["pit"]["seconds"] == pytest.approx(65.0)   # la espera inicial no cuenta
    assert stops[0]["driverIn"] == "Ben B"


def test_car_pit_summary(client, tmp_path):
    # FP1 #007: una sola parada, con relevo Ana -> Ben
    body = client.get("/api/sessions/FP1.csv/cars/007").json()
    summary = body["pitSummary"]
    assert summary["withChange"]["count"] == 1
    assert summary["withChange"]["mean"]["seconds"] == body["pitStops"][0]["pit"]["seconds"]
    assert summary["withoutChange"]["count"] == 0
    assert summary["withoutChange"]["mean"] == {"seconds": None, "text": "–"}
    assert [d["meanGap"] for d in body["drivers"]] == [
        {"seconds": 0.0, "text": "Referencia"}, {"seconds": 0.0, "text": "Referencia"},
    ]

    # una parada sin relevo (30 s, sigue Ana) y otra con relevo (50 s, entra Ben)
    pace = lambda s, d: (s, d, None, False, "GF")  # noqa: E731
    write_session(tmp_path / "PIT.csv", car_rows("5", [
        (120.0, "Ana A", None, False, "GF"),
        pace(94.0, "Ana A"), pace(94.1, "Ana A"),
        (110.0, "Ana A", None, True, "GF"),     # 4: entrada
        (125.0, "Ana A", 30.0, False, "GF"),    # 5: salida, mismo piloto
        pace(94.2, "Ana A"),
        (111.0, "Ana A", None, True, "GF"),     # 7: entrada
        (140.0, "Ben B", 50.0, False, "GF"),    # 8: salida, entra Ben
        pace(94.3, "Ben B"),
    ]))
    body = client.get("/api/sessions/PIT.csv/cars/5").json()
    assert [(s["fromLap"], s["toLap"], s["driverChange"]) for s in body["pitStops"]] == [
        (4, 5, False), (7, 8, True),
    ]
    summary = body["pitSummary"]
    assert summary["withoutChange"]["count"] == 1
    assert summary["withoutChange"]["mean"]["seconds"] == pytest.approx(30.0)
    assert summary["withChange"]["mean"]["seconds"] == pytest.approx(50.0)
    assert summary["withChange"]["best"]["seconds"] == pytest.approx(50.0)


def test_shared_number_is_separated_not_rejected(client, tmp_path):
    # El mismo FP1 pero "guardado con Excel": 007 -> 7, igual que el Toyota
    lost = [r.replace("007;", "7;", 1) if r.startswith("007;") else r for r in SESSION_ROWS]
    write_session(tmp_path / "LOST.csv", lost)

    overview = client.get("/api/sessions/LOST.csv/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["cars"] == 3 and len(body["notices"]) == 1 and "Excel" in body["notices"][0]

    cat = client.get("/api/sessions/LOST.csv/categories/HYPERCAR").json()
    assert [c["number"] for c in cat["cars"]] == ["7 (Aston)", "7 (Toyota)"]
    car = client.get("/api/sessions/LOST.csv/cars/7%20(Aston)").json()
    assert len(car["laps"]) == 8 and [d["name"] for d in car["drivers"]] == ["Ana A", "Ben B"]


def test_repeated_laps_are_reported(client, tmp_path):
    # Una vuelta repetida (como pasa si el #007 y el #7 se leen como el mismo coche)
    write_session(tmp_path / "DUP.csv", SESSION_ROWS + [SESSION_ROWS[9]])
    reply = client.get("/api/sessions/DUP.csv/overview")
    assert reply.status_code == 422
    assert "vueltas repetidas" in reply.json()["detail"]


def _two_sessions(tmp_path):
    """FP2: el #7 mejora su vuelta (92.0) y sus sectores 1 y 3; el #99 va más lento."""
    pace = lambda s, d: (s, d, None, False, "GF")  # noqa: E731
    first = (120.0, "Carl C", None, False, "GF")
    write_session(tmp_path / "FP2.csv",
                  car_rows("7", [first, pace(92.0, "Carl C"), pace(93.0, "Carl C")], team="Toyota")
                  + car_rows("99", [(130.0, "Dan D", None, False, "GF"), pace(102.0, "Dan D")],
                             category="LMGT3", team="Ford"))


def test_overall_session_joins_all_sessions(client, tmp_path):
    _two_sessions(tmp_path)
    listing = client.get("/api/sessions").json()["sessions"]
    assert [s["id"] for s in listing] == ["FP1.csv", "FP2.csv", "__all__"]
    last = listing[-1]
    assert (last["id"], last["name"], last["overall"], last["event"]) == (
        "__all__", "Todas las sesiones", True, ".")
    assert last["categories"] == ["HYPERCAR", "LMGT3"]

    ov = client.get("/api/sessions/__all__/overview").json()
    assert (ov["overall"], ov["sessionCount"], ov["laps"], ov["cars"]) == (True, 2, 17, 3)
    assert ov["session"]["name"] == "Todas las sesiones" and ov["clockStart"] == ""
    hyper = ov["categories"][0]
    assert hyper["bestLap"]["text"] == "01:32.000" and hyper["bestLap"]["session"] == "FP2"

    bests = {b["key"]: b for b in client.get("/api/sessions/__all__/categories/HYPERCAR").json()["bests"]}
    assert (bests["lap"]["car"], bests["lap"]["session"], bests["lap"]["lap"]) == ("7", "FP2", 2)
    assert bests["s1"]["session"] == "FP2" and bests["s3"]["session"] == "FP2"
    assert bests["s2"]["session"] == "FP1"          # el mejor sector 2 es de la FP1
    gt3 = client.get("/api/sessions/__all__/categories/LMGT3").json()
    assert gt3["bests"][0]["session"] == "FP1"      # 101.5 (FP1) mejora a 102.0 (FP2)
    ranking = client.get("/api/sessions/__all__/categories/HYPERCAR").json()["rankings"]["lap"]
    assert [(r["car"], r["session"]) for r in ranking] == [("7", "FP2"), ("007", "FP1")]


def test_overall_laps_are_accumulated_per_car(client, tmp_path):
    _two_sessions(tmp_path)
    car = client.get("/api/sessions/__all__/cars/7").json()
    assert [(l["lap"], l["session"], l["sessionLap"]) for l in car["laps"]] == [
        (1, "FP1", 1), (2, "FP1", 2), (3, "FP2", 1), (4, "FP2", 2), (5, "FP2", 3),
    ]
    # la primera vuelta de cada sesión es de salida: arranca un stint nuevo
    assert [(s["stint"], s["startLap"], s["endLap"]) for s in car["stints"]] == [(1, 1, 2), (2, 3, 5)]
    assert car["pitStops"] == []                    # el salto de FP1 a FP2 no es una parada
    pace = client.get("/api/sessions/__all__/categories/HYPERCAR").json()["pace"][0]
    assert [(p["lap"], p["session"], p["sessionLap"]) for p in pace["laps"]] == [
        (2, "FP1", 2), (4, "FP2", 2), (5, "FP2", 3),
    ]
    assert client.get("/api/sessions/FP2.csv/cars/7").json()["laps"][0]["session"] == "FP2"


def test_overall_needs_more_than_one_file(client):
    assert client.get("/api/sessions/__all__/overview").status_code == 404


def test_errors(client):
    assert client.get("/api/sessions/nope.csv/overview").status_code == 404
    assert client.get("/api/sessions/..%2Fsecret.csv/overview").status_code == 404
    assert client.get("/api/sessions/FP1.csv/categories/LMP2").status_code == 404
    assert client.get("/api/sessions/FP1.csv/cars/999").status_code == 404
    assert client.get("/api/sessions/FP1.csv/categories/HYPERCAR?slow=50").status_code == 422


def test_cors_allows_the_vite_origin(client):
    reply = client.get("/api/sessions", headers={"Origin": "http://localhost:5173"})
    assert reply.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.fixture()
def events_client(tmp_path, monkeypatch):
    """Dos eventos en subcarpetas: WEC/2026/Barcelona (2 sesiones) y ALMS/paul-ricard (2 sesiones LMP2)."""
    pace = lambda s, d: (s, d, None, False, "GF")  # noqa: E731
    out = (120.0, "Ann", None, False, "GF")
    for folder in ("WEC/2026/Barcelona", "ALMS/paul-ricard"):
        (tmp_path / folder).mkdir(parents=True)
    write_session(tmp_path / "WEC/2026/Barcelona/FP1.csv", SESSION_ROWS)
    write_session(tmp_path / "WEC/2026/Barcelona/FP2.csv", SESSION_ROWS)
    lmp2_1 = car_rows("5", [out, pace(98.0, "Ann"), pace(98.5, "Ann")], category="LMP2", team="Oreca A")
    lmp2_1 += car_rows("6", [out, pace(99.0, "Bob"), pace(99.5, "Bob")], category="LMP2", team="Oreca B")
    lmp2_2 = car_rows("5", [out, pace(97.5, "Ann"), pace(98.0, "Ann")], category="LMP2", team="Oreca A")
    write_session(tmp_path / "ALMS/paul-ricard/R1.csv", lmp2_1)
    write_session(tmp_path / "ALMS/paul-ricard/R2.csv", lmp2_2)
    (tmp_path / "ALMS/paul-ricard/~$R1.csv").write_text("temporal de Excel")   # debe ignorarse
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    api._load.cache_clear()
    api._marked.cache_clear()
    api._overall.cache_clear()
    return TestClient(api.app)


def test_events_in_subfolders(events_client):
    sessions = events_client.get("/api/sessions").json()["sessions"]
    assert [s["id"] for s in sessions] == [
        "ALMS/paul-ricard/R1.csv", "ALMS/paul-ricard/R2.csv", "ALMS/paul-ricard/__all__",
        "WEC/2026/Barcelona/FP1.csv", "WEC/2026/Barcelona/FP2.csv", "WEC/2026/Barcelona/__all__",
    ]
    alms, wec = sessions[0], sessions[3]
    assert (alms["event"], alms["eventName"], alms["categories"]) == ("ALMS/paul-ricard", "ALMS · Paul Ricard", ["LMP2"])
    assert (wec["event"], wec["eventName"]) == ("WEC/2026/Barcelona", "WEC · 2026 · Barcelona")
    assert sessions[2]["categories"] == ["LMP2"] and sessions[2]["overall"] is True


def test_lmp2_session_in_a_subfolder(events_client):
    ov = events_client.get("/api/sessions/ALMS/paul-ricard/R1.csv/overview").json()
    assert [(c["id"], c["label"], c["cars"]) for c in ov["categories"]] == [("LMP2", "LMP2", 2)]
    assert ov["session"]["eventName"] == "ALMS · Paul Ricard"
    cat = events_client.get("/api/sessions/ALMS/paul-ricard/R1.csv/categories/LMP2").json()
    assert [r["car"] for r in cat["rankings"]["lap"]] == ["5", "6"]
    assert cat["bests"][0]["text"] == "01:38.000"
    car = events_client.get("/api/sessions/ALMS/paul-ricard/R1.csv/cars/5").json()
    assert car["car"]["category"] == "LMP2" and len(car["laps"]) == 3


def test_overall_only_joins_its_own_event(events_client):
    ov = events_client.get("/api/sessions/ALMS/paul-ricard/__all__/overview").json()
    assert (ov["overall"], ov["sessionCount"], ov["cars"], ov["laps"]) == (True, 2, 2, 9)
    assert ov["session"]["event"] == "ALMS/paul-ricard"
    best = events_client.get("/api/sessions/ALMS/paul-ricard/__all__/categories/LMP2").json()["bests"][0]
    assert (best["text"], best["session"], best["car"]) == ("01:37.500", "R2", "5")
    wec = events_client.get("/api/sessions/WEC/2026/Barcelona/__all__/overview").json()
    assert [c["id"] for c in wec["categories"]] == ["HYPERCAR", "LMGT3"]