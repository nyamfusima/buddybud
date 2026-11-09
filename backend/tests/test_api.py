import io

from sqlalchemy import select

from app.db.models import Agent, User
from tests.conftest import login


def test_login_rejects_bad_password(client, seeded):
    r = client.post("/api/auth/login", json={"email": seeded["logins"]["agent"], "password": "nope"})
    assert r.status_code == 401


def test_agent_dashboard_bundle_shape(client, seeded):
    h = login(client, seeded["logins"]["agent"])
    r = client.get("/api/me/dashboard", headers=h)
    assert r.status_code == 200
    body = r.json()
    data, shared, coaching = body["data"], body["shared"], body["coaching"]
    for key in ("agent", "tl", "om", "tenure", "all_rows", "detractors", "win_candidates", "vuln", "team_nps", "hist_avg_monthly_n"):
        assert key in data
    assert shared["nps_target"] == 40 and shared["date_max"] <= "2026-11-08"
    assert "Unaccommodating" in coaching["people"] and coaching["general_process_closer"]


def test_agent_cannot_reach_manager_endpoints(client, seeded):
    h = login(client, seeded["logins"]["agent"])
    assert client.get("/api/team/overview", headers=h).status_code == 403
    assert client.get("/api/insights/summary", headers=h).status_code == 403
    assert client.get("/api/admin/status", headers=h).status_code == 403


def test_tl_sees_only_their_team(client, seeded, db):
    tl_email = seeded["logins"]["tl"]
    tl = db.scalars(select(User).where(User.email == tl_email)).one()
    h = login(client, tl_email)
    rows = client.get("/api/team/overview", headers=h).json()["agents"]
    assert rows and all(r["tl"] == tl.scope_name for r in rows)
    other = db.scalars(select(Agent).where(Agent.tl_name != tl.scope_name)).first()
    assert client.get(f"/api/team/agents/{other.id}/dashboard", headers=h).status_code == 404
    mine = rows[0]["agent_id"]
    assert client.get(f"/api/team/agents/{mine}/dashboard", headers=h).status_code == 200


def test_insights_and_forecast(client, seeded):
    h = login(client, seeded["logins"]["admin"])
    s = client.get("/api/insights/summary", headers=h).json()
    assert s["tenure_curve"] and s["tl_outliers"]
    assert any(t["new_share"] == 100.0 for t in s["new_teams"])
    f = client.post("/api/insights/hiring-forecast", headers=h,
                    json={"planned": [{"go_live": "2026-12-01", "count": 40}], "months": 4}).json()
    assert len(f["baseline"]) == 4 and len(f["with_plan"]) == 4
    assert f["with_plan"][1]["expected_nps"] < f["baseline"][1]["expected_nps"]  # a wave drags the forecast down


def test_survey_import_validates_rows(client, seeded):
    h = login(client, seeded["logins"]["admin"])
    csv = ("Survey ID,Employee ID,Survey Date,NPS Score,OSAT,Verbatim\n"
           "NEW1,E1001,2026-11-08,3,2,Agent was rude and dismissive\n"
           "NEW2,NOPE,2026-11-08,9,5,great\n"
           "NEW3,E1001,2026-11-08,14,5,bad score\n")
    r = client.post("/api/admin/import/surveys", headers=h, files={"file": ("s.csv", io.BytesIO(csv.encode()), "text/csv")})
    body = r.json()
    assert r.status_code == 200, body
    assert body["rows_ok"] == 1 and body["rows_bad"] == 2
    assert body["classification"]["classified"] >= 1


def test_password_change_flow(client, seeded):
    h = login(client, seeded["logins"]["om"])
    bad = client.post("/api/auth/change-password", headers=h, json={"current_password": "BuddyBud2026!", "new_password": "short"})
    assert bad.status_code == 400
    ok = client.post("/api/auth/change-password", headers=h, json={"current_password": "BuddyBud2026!", "new_password": "NewPassw0rd"})
    assert ok.status_code == 200
    login(client, seeded["logins"]["om"], "NewPassw0rd")
