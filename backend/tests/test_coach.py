import json

from app.agents.coach.graph import ungrounded_numbers
from app.agents.coach.safety import keyword_screen
from tests.conftest import login


def _events(text: str) -> list[tuple[str, object]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_safety_screen():
    assert keyword_screen("honestly I want to kill myself")
    assert keyword_screen("my TL has been threatening me")
    assert not keyword_screen("my NPS is killing me lol")


def test_grounding_flags_invented_numbers():
    evidence = ['{"nps": 22.5, "osat": 61.0, "surveys": 40}', "target NPS 40"]
    assert ungrounded_numbers("You're on 22.5 NPS, 17.5 below target, over 40 surveys.", evidence) == []
    assert ungrounded_numbers("Your NPS is 63.2 this week.", evidence) == ["63.2"]
    assert ungrounded_numbers("Try it on your next 5 calls.", evidence) == []


def test_chat_uses_tools_and_persists(client, seeded):
    h = login(client, seeded["logins"]["agent"])
    client.delete("/api/coach/history", headers=h)
    r = client.post("/api/coach/chat", headers=h, json={"message": "How's my NPS looking?"})
    assert r.status_code == 200
    ev = _events(r.text)
    kinds = [e for e, _ in ev]
    assert "status" in kinds and kinds[-1] == "done"
    final = ev[-1][1]["text"]
    assert "NPS" in final
    hist = client.get("/api/coach/history", headers=h).json()["messages"]
    assert [m["role"] for m in hist][-2:] == ["user", "assistant"]


def test_crisis_gets_fixed_reply(client, seeded):
    h = login(client, seeded["logins"]["agent"])
    r = client.post("/api/coach/chat", headers=h, json={"message": "I can't do this anymore, I want to end my life"})
    ev = _events(r.text)
    assert ev[-1][0] == "done" and ev[-1][1]["safety"] == "crisis"
    assert "Employee Assistance" in ev[-1][1]["text"] or "EAP" in ev[-1][1]["text"]


def test_managers_without_agent_record_cannot_chat(client, seeded):
    h = login(client, seeded["logins"]["admin"])
    assert client.post("/api/coach/chat", headers=h, json={"message": "hi"}).status_code == 400
