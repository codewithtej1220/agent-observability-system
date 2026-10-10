from scripts.bootstrap import run_to_payload


def _payload(run):
    return run_to_payload(run, None).model_dump(mode="json")


def test_health_is_public(client):
    r = client.get("/health", headers={"X-API-Key": ""})
    assert r.status_code == 200 and r.json()["models_loaded"]


def test_auth_required(client):
    assert client.get("/api/overview", headers={"X-API-Key": ""}).status_code == 401
    assert client.get("/api/overview", headers={"X-API-Key": "wrong"}).status_code == 403


def test_ingest_full_run_and_detail(client, make_run):
    run = make_run("loop", agent="research-agent", seed=21)
    r = client.post("/api/ingest/runs", json=_payload(run))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["severity"] != "healthy" and body["failure_type"] == "loop"
    assert body["first_flag_step"] is not None

    d = client.get(f"/api/runs/{run.run_id}").json()
    assert len(d["steps"]) == len(run.steps)
    assert len(d["risk_trajectory"]) == len(run.steps)
    assert any(s["evidence"] for s in d["steps"])

    assert client.post("/api/ingest/runs", json=_payload(run)).status_code == 409


def test_streaming_flow(client, make_run):
    run = make_run("hallucinated_tool", agent="travel-planner", seed=8)
    start = client.post("/api/ingest/runs/start", json={"agent_id": run.agent_id, "task": run.task, "model": run.model})
    run_id = start.json()["run_id"]
    severities = []
    for s in run.steps:
        step = {"type": s.type, "tool_name": s.tool_name, "arguments": s.arguments, "output": s.output,
                "status": s.status, "input_tokens": s.input_tokens, "output_tokens": s.output_tokens}
        r = client.post(f"/api/ingest/runs/{run_id}/steps", json=step)
        assert r.status_code == 200, r.text
        severities.append(r.json()["severity"])
    assert severities[-1] != "healthy"
    fin = client.post(f"/api/ingest/runs/{run_id}/finish").json()
    assert fin["step_count"] == len(run.steps)


def test_feedback_updates_policy(client, make_run):
    from app.services.registry import registry

    run = make_run("tool_thrashing", agent="data-analyst", seed=13)
    client.post("/api/ingest/runs", json=_payload(run))
    before = registry.policy.n_updates
    r = client.post(f"/api/runs/{run.run_id}/feedback", json={"label": "tool_thrashing", "resolved": True})
    assert r.status_code == 200, r.text
    assert r.json()["policy_updated"]
    assert registry.policy.n_updates == before + 1
    assert client.post(f"/api/runs/{run.run_id}/feedback", json={"label": "nonsense", "resolved": True}).status_code == 422


def test_dashboard_endpoints(client, make_run):
    client.post("/api/ingest/runs/batch", json=[_payload(make_run(l, seed=40 + i))
                                                 for i, l in enumerate(["healthy", "loop", "token_waste"])])
    for path in ["/api/meta", "/api/overview?hours=24", "/api/runs?severity=flagged", "/api/agents",
                 "/api/agents/support-bot", "/api/agents/compare?ids=support-bot,research-agent",
                 "/api/review-queue", "/api/behavior-map", "/api/policy", "/api/models"]:
        r = client.get(path)
        assert r.status_code == 200, (path, r.text)
    ov = client.get("/api/overview?hours=24").json()
    assert ov["kpis"]["runs"] >= 3
    graph = client.get("/api/agents/support-bot").json()["tool_graph"]
    assert any(n["id"] == "START" for n in graph["nodes"]) and graph["edges"]


def test_not_found_and_validation(client):
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/agents/missing").status_code == 404
    assert client.post("/api/ingest/runs", json={"agent_id": "a", "steps": []}).status_code == 422
    assert client.post("/api/ingest/runs", json={"agent_id": "a", "steps": [{"type": "bogus"}]}).status_code == 422
