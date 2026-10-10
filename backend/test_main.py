from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "courses": 234}


def test_list_paginates():
    r = client.get("/api/courses", params={"limit": 10, "offset": 5}).json()
    assert r["total"] == 234
    assert len(r["courses"]) == 10


def test_filter_by_category_is_case_insensitive():
    r = client.get("/api/courses", params={"category": "artificial intelligence"}).json()
    assert r["total"] == 3
    assert all(c["course_category"] == "Artificial Intelligence" for c in r["courses"])


def test_room_shorthand_matches_full_name():
    short = client.get("/api/courses", params={"room": "2400"}).json()
    full = client.get("/api/courses", params={"room": "EVANS 2400"}).json()
    assert short["total"] == full["total"] > 0


def test_day_filter():
    r = client.get("/api/courses", params={"day": "Fr", "limit": 500}).json()
    assert r["total"] > 0
    assert all("F" in c["daytimes"] for c in r["courses"])


def test_search():
    r = client.get("/api/courses", params={"q": "Managing Groups"}).json()
    assert {c["course_number"] for c in r["courses"]} == {"MGT 401", "MGT 636"}


def test_course_detail_and_404():
    first = client.get("/api/courses", params={"limit": 1}).json()["courses"][0]
    r = client.get(f"/api/courses/{first['id']}")
    assert r.status_code == 200
    assert r.json()["course_title"] == first["course_title"]
    assert client.get("/api/courses/999999").status_code == 404


def test_categories_skip_blank():
    cats = client.get("/api/categories").json()
    assert cats[0] == {"name": "Core", "count": 45}
    assert all(c["name"] for c in cats)


def test_rooms_and_room_courses():
    rooms = client.get("/api/rooms").json()
    assert {"name": "EVANS 4200", "count": 19} in rooms
    assert all(r["name"] for r in rooms)
    assert len(client.get("/api/rooms/4200/courses").json()) == 19
    assert client.get("/api/rooms/9999/courses").status_code == 404


def test_faculty():
    people = client.get("/api/faculty").json()
    assert len(people) == 109  # 27 courses list no faculty and are skipped
    assert any(p["name"] == "DiBenigno, Julia" and "MGT 401" in p["courses"] for p in people)


def test_no_emails_exposed():
    detail = client.get("/api/courses/1").json()
    assert "faculty_1_email" not in detail


def test_cors_allows_vite_dev_server():
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


# ---------- professor agents (the model is faked: these tests make no network calls)

import professors  # noqa: E402


def test_professors_list_and_detail():
    profs = client.get("/api/professors").json()
    assert len(profs) == 109
    zaman = next(p for p in profs if p["slug"] == "tauhid-zaman")
    assert zaman == {"slug": "tauhid-zaman", "name": "Tauhid Zaman", "courses": ["MGT 409"], "has_style": True}
    d = client.get("/api/professors/tauhid-zaman").json()
    assert d["greeting"].startswith("Yo")
    assert "Operations Management" in d["bio"]
    assert client.get("/api/professors/nobody-here").status_code == 404


def test_system_prompt_uses_catalog_and_style():
    import db

    conn = db.connect()
    prompt = professors.system_prompt(db.professor(conn, "tauhid-zaman"))
    conn.close()
    assert "MGT 409 AI Foundations for Managers" in prompt
    assert "EVANS 2200" in prompt  # meeting rooms come from the catalog
    assert '"yo"' in prompt and "Labubu" in prompt
    assert "pedantic" in prompt


def test_tools_hit_the_database():
    hits = professors.run_tool("search_courses", {"category": "Artificial Intelligence"})
    assert hits["total_matches"] == 3
    assert professors.run_tool("get_professor", {"name": "zaman"})["courses"][0]["course_number"] == "MGT 409"
    assert "ambiguous" in professors.run_tool("get_professor", {"name": "a"})
    assert "error" in professors.run_tool("get_course_details", {"course_id": 999999})
    assert professors.run_tool("list_categories", {})[0]["name"] == "Core"


def test_chat_runs_tool_loop(monkeypatch):
    class Call:
        type = "function_call"
        name = "search_courses"
        arguments = '{"query": "Corporate Finance"}'
        call_id = "c1"

        def model_dump(self, **_):
            return {"type": "function_call", "name": self.name, "arguments": self.arguments, "call_id": self.call_id}

    class Resp:
        def __init__(self, output, text=""):
            self.output = output
            self.output_text = text

    seen = []

    class FakeResponses:
        def create(self, **kw):
            seen.append(kw)
            if len(seen) == 1:
                return Resp([Call()])
            return Resp([], "Yo, MGT 541 is Heather Tookes.")

    class FakeClient:
        responses = FakeResponses()

    monkeypatch.setattr(professors, "client", lambda: FakeClient())
    r = client.post("/api/professors/tauhid-zaman/chat", json={"messages": [{"role": "user", "content": "who teaches corp fin?"}]})
    assert r.status_code == 200
    assert r.json() == {"reply": "Yo, MGT 541 is Heather Tookes.", "tools_used": ["search_courses"]}
    tool_output = seen[1]["input"][-1]
    assert tool_output["type"] == "function_call_output" and "Tookes" in tool_output["output"]
    assert seen[0]["model"] == professors.MODEL


def test_chat_validates_input():
    assert client.post("/api/professors/tauhid-zaman/chat", json={"messages": []}).status_code == 422
    last_not_user = {"messages": [{"role": "assistant", "content": "hi"}]}
    assert client.post("/api/professors/tauhid-zaman/chat", json=last_not_user).status_code == 422
    assert client.post("/api/professors/nobody/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 404
