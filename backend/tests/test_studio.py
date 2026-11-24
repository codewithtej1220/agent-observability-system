"""Sessions, trace linking, prompt management, datasets and experiments."""
from test_gateway import CHAT, gw  # noqa: F401  (fixture)


def test_sessions_group_calls_in_order(gw):  # noqa: F811
    gw.mock.texts = ["Paris.", "Berlin.", "Rome."]
    for q in ("France?", "Germany?"):
        body = {**CHAT, "messages": [{"role": "user", "content": f"Capital of {q}"}]}
        assert gw.openai(body, **{"X-AOBS-Session": "conv-1", "X-AOBS-User": "u-42"}).status_code == 200
    gw.openai(CHAT, **{"X-AOBS-Session": "conv-2"})
    gw.openai(CHAT)  # no session: not listed

    s = gw.dash.get("/api/llm/sessions").json()
    assert s["total"] == 2
    first = next(x for x in s["items"] if x["session_id"] == "conv-1")
    assert first["calls"] == 2 and first["end_user"] == "u-42" and first["preview"] == "Capital of France?"

    d = gw.dash.get("/api/llm/sessions/conv-1").json()
    assert [c["last_user"] for c in d["calls"]] == ["Capital of France?", "Capital of Germany?"]
    assert [c["response_text"] for c in d["calls"]] == ["Paris.", "Berlin."]
    assert d["totals"]["calls"] == 2
    assert gw.dash.get("/api/llm/sessions/nope").status_code == 404


def test_gateway_calls_link_to_agent_run_steps(gw):  # noqa: F811
    run_id = gw.dash.post("/api/ingest/runs/start", json={"agent_id": "trace-bot", "task": "t"}).json()["run_id"]
    gw.openai(CHAT, **{"X-AOBS-Run": run_id, "X-AOBS-Step": "0"})
    gw.dash.post(f"/api/ingest/runs/{run_id}/steps", json={"type": "llm", "output": "thinking"})
    gw.openai(CHAT, **{"X-AOBS-Run": run_id, "X-AOBS-Step": "not-a-number"})  # malformed step: ignored, not rejected
    gw.openai(CHAT)  # unrelated call

    calls = gw.dash.get(f"/api/runs/{run_id}").json()["llm_calls"]
    assert [(c["run_id"], c["run_step"]) for c in calls] == [(run_id, 0), (run_id, None)]


def test_prompt_versions_labels_and_resolve(gw):  # noqa: F811
    d = gw.dash
    v1 = d.post("/api/llm/prompts", json={"name": "support", "template": "Help with: {{input}}", "labels": ["production"]}).json()
    v2 = d.post("/api/llm/prompts", json={"name": "support", "template": "Be brief. {{input}}", "labels": ["staging"]}).json()
    assert (v1["version"], v2["version"]) == (1, 2) and "latest" in v2["labels"]

    assert d.get("/api/llm/prompts/support/resolve").json()["version"] == 1           # production by default
    assert d.get("/api/llm/prompts/support/resolve?label=latest").json()["version"] == 2
    assert d.get("/api/llm/prompts/support/resolve?label=staging").json()["version"] == 2
    assert d.get("/api/llm/prompts/support/resolve?label=nope").status_code == 404

    # Moving "production" to v2 takes it off v1.
    d.put("/api/llm/prompts/support/versions/2/labels", json={"labels": ["production"]})
    vs = {v["version"]: v["labels"] for v in d.get("/api/llm/prompts/support").json()["versions"]}
    assert vs[1] == [] and set(vs[2]) == {"production", "latest"}
    assert d.post("/api/llm/prompts", json={"name": "support", "labels": ["latest"]}).status_code == 422

    # Calls record the version they used; the prompt page counts them.
    gw.openai(CHAT, **{"X-AOBS-Prompt": "support@2"})
    assert (gw.last_call()["prompt_name"], gw.last_call()["prompt_version"]) == ("support", 2)
    usage = {v["version"]: v["usage"] for v in d.get("/api/llm/prompts/support").json()["versions"]}
    assert usage[2]["calls"] == 1 and usage[1] is None
    assert d.get("/api/llm/prompts").json()[0]["labels"] == {"production": 2}


def test_dataset_experiment_scores_each_item(gw):  # noqa: F811
    d = gw.dash
    contract = gw.contract(name="Short", slug="short", rules=[{"type": "max_words", "params": {"value": 5}, "severity": "critical"}])
    ds = d.post("/api/llm/datasets", json={"name": "geo"}).json()
    assert d.post("/api/llm/datasets", json={"name": "geo"}).status_code == 409
    assert d.post(f"/api/llm/datasets/{ds['id']}/experiments",
                  json={"name": "x", "provider": "openai", "model": "gpt-4o-mini"}).status_code == 422  # empty

    d.post(f"/api/llm/datasets/{ds['id']}/items", json={"input": "Capital of France?", "expected": "Paris."})
    gw.mock.texts = ["Rome is the capital."]
    gw.openai({**CHAT, "messages": [{"role": "user", "content": "Capital of Italy?"}]})
    item = d.post(f"/api/llm/datasets/{ds['id']}/items/from-call", json={"call_id": gw.last_call()["id"]}).json()
    assert item["input"] == "Capital of Italy?" and item["expected"] == "Rome is the capital."

    d.post("/api/llm/prompts", json={"name": "geo", "template": "Answer: {{input}}"})
    gw.mock.texts = ["Paris.", "Rome is the capital of Italy, a country in southern Europe with a long history."]
    e = d.post(f"/api/llm/datasets/{ds['id']}/experiments", json={
        "name": "baseline", "provider": "openai", "model": "gpt-4o-mini", "prompt_name": "geo", "contract_id": contract["id"]}).json()
    assert e["prompt_version"] == 1

    r = d.get(f"/api/llm/experiments/{e['id']}").json()  # TestClient runs the background task before returning
    assert r["status"] == "done", r
    assert [x["passed"] for x in r["results"]] == [True, False]  # second answer breaks the 5-word rule
    assert r["results"][0]["similarity"] == 1.0
    assert r["summary"]["pass_rate"] == 0.5 and r["summary"]["errors"] == 0
    sent = [req for req in gw.mock.requests if req.url.path.endswith("/chat/completions")][-2:]
    assert b"Answer: Capital of France?" in sent[0].content  # prompt template applied

    # Experiment calls are recorded but kept out of the live feed.
    live = d.get("/api/llm/calls").json()["items"]
    assert all(c["source"] != "experiment" for c in live)
    assert d.get("/api/llm/calls?source=experiment").json()["total"] == 2

    assert d.delete(f"/api/llm/datasets/{ds['id']}").json() == {"ok": True}
    assert d.get(f"/api/llm/experiments/{e['id']}").status_code == 404


def test_experiment_without_credential_reports_error(new_user):
    dash, _ = new_user()
    ds = dash.post("/api/llm/datasets", json={"name": "d"}).json()
    dash.post(f"/api/llm/datasets/{ds['id']}/items", json={"input": "hi"})
    e = dash.post(f"/api/llm/datasets/{ds['id']}/experiments", json={"name": "x", "provider": "openai", "model": "m"}).json()
    r = dash.get(f"/api/llm/experiments/{e['id']}").json()
    assert r["status"] == "error" and "credential" in r["detail"]


def test_sdk_prompt_and_run_headers():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk"))
    from agent_observability import LiveRun, ManagedPrompt

    p = ManagedPrompt({"name": "support", "version": 3, "template": "Hi {{name}}, re: {{topic}}"})
    assert p.compile(name="Sam", topic="refund") == "Hi Sam, re: refund"
    assert p.headers == {"X-AOBS-Prompt": "support@3"}

    run = LiveRun(client=None, agent_id="a", task="", model="", run_id="r-1")
    assert run.gateway_headers() == {"X-AOBS-Run": "r-1", "X-AOBS-Step": "0"}
    run.steps = 2
    assert run.gateway_headers()["X-AOBS-Step"] == "2"
    run._disabled = True
    assert run.gateway_headers() == {}
