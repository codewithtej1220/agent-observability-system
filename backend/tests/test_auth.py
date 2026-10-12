from scripts.bootstrap import run_to_payload


def _payload(run):
    return run_to_payload(run, None).model_dump(mode="json")


def test_signup_login_logout(new_user):
    c, email = new_user()
    me = c.get("/api/auth/me").json()
    assert me["user"]["email"] == email and me["workspace"]["role"] == "admin"

    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401

    bad = c.post("/api/auth/login", json={"email": email, "password": "wrong-password-1"})
    assert bad.status_code == 401
    ok = c.post("/api/auth/login", json={"email": email.upper(), "password": "correct-horse-9"})
    assert ok.status_code == 200
    assert c.get("/api/auth/me").status_code == 200


def test_signup_validation(new_user, client):
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    c.headers.update({"X-Requested-With": "aobs"})
    assert c.post("/api/auth/signup", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert c.post("/api/auth/signup", json={"email": "not-an-email", "password": "long-enough-1"}).status_code == 422
    _, email = new_user()
    assert c.post("/api/auth/signup", json={"email": email, "password": "another-pass-1"}).status_code == 409


def test_csrf_header_required_for_session_writes(new_user):
    c, _ = new_user()
    r = c.post("/api/workspace/api-keys", json={"name": "k"}, headers={"X-Requested-With": ""})
    assert r.status_code == 403
    assert c.post("/api/workspace/api-keys", json={"name": "k"}).status_code == 200


def test_session_cookie_is_httponly(new_user):
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    r = c.post("/api/auth/signup", json={"email": "cookie@example.com", "password": "cookie-pass-1"},
               headers={"X-Requested-With": "aobs"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_api_key_lifecycle_and_workspace_isolation(new_user, make_run):
    a, _ = new_user()
    b, _ = new_user()
    key = a.post("/api/workspace/api-keys", json={"name": "ci"}).json()["key"]
    assert key.startswith("aobs_")

    from fastapi.testclient import TestClient

    from app.main import app

    sdk = TestClient(app)
    run = make_run("loop", agent="research-agent", seed=77)
    r = sdk.post("/api/ingest/runs", json=_payload(run), headers={"X-API-Key": key})
    assert r.status_code == 200, r.text

    assert a.get(f"/api/runs/{run.run_id}").status_code == 200
    assert b.get(f"/api/runs/{run.run_id}").status_code == 404          # other workspace
    assert b.get("/api/runs").json()["total"] == 0

    key_id = a.get("/api/workspace/api-keys").json()[0]["id"]
    assert a.delete(f"/api/workspace/api-keys/{key_id}").status_code == 200
    assert sdk.get("/api/runs", headers={"X-API-Key": key}).status_code == 401


def test_provider_keys_are_encrypted(new_user):
    from app.db import SessionLocal
    from app.orm import ProviderCredential

    c, _ = new_user()
    secret = "sk-test-0123456789abcdef"
    r = c.post("/api/workspace/credentials", json={"provider": "openai", "api_key": secret})
    assert r.status_code == 200
    out = r.json()
    assert out["key_hint"] == "…cdef" and "api_key" not in out and "encrypted_key" not in out
    listed = c.get("/api/workspace/credentials").text
    assert secret not in listed

    db = SessionLocal()
    row = db.get(ProviderCredential, out["id"])
    assert row.encrypted_key != secret and secret not in row.encrypted_key
    from app.crypto import decrypt
    assert decrypt(row.encrypted_key) == secret
    db.close()


def test_roles(new_user, make_run):
    admin, _ = new_user()
    viewer, viewer_email = new_user()
    assert admin.post("/api/workspace/members", json={"email": viewer_email, "role": "viewer"}).status_code == 200
    ws_id = admin.get("/api/auth/me").json()["workspace"]["id"]
    assert viewer.post("/api/auth/switch-workspace", json={"workspace_id": ws_id}).status_code == 200
    assert viewer.get("/api/auth/me").json()["workspace"]["role"] == "viewer"

    # Viewers can read but not write.
    assert viewer.get("/api/overview").status_code == 200
    assert viewer.post("/api/ingest/runs", json=_payload(make_run(seed=3))).status_code == 403
    assert viewer.post("/api/workspace/credentials", json={"provider": "openai", "api_key": "sk-xxxxxxxxxxxx"}).status_code == 403

    # The last admin cannot be demoted.
    me_id = admin.get("/api/auth/me").json()["user"]["id"]
    assert admin.patch(f"/api/workspace/members/{me_id}", json={"role": "member"}).status_code == 409


def test_google_sign_in(client, monkeypatch):
    from fastapi.testclient import TestClient

    from app import routes_account
    from app.main import app

    async def fake_exchange(code):
        assert code == "auth-code"
        return {"sub": "google-123", "email": "Gina@Example.com", "email_verified": True, "name": "Gina"}

    monkeypatch.setattr(routes_account, "google_exchange", fake_exchange)
    c = TestClient(app, follow_redirects=False)
    start = c.get("/api/auth/google/login")
    assert start.status_code == 302 and "accounts.google.com" in start.headers["location"]
    state = start.headers["location"].split("state=")[1].split("&")[0]

    # Forged state is rejected.
    bad = c.get("/api/auth/google/callback", params={"code": "auth-code", "state": "forged"})
    assert "/login?error=" in bad.headers["location"]

    c.cookies.set("aobs_oauth_state", state, path="/api/auth/google")
    ok = c.get("/api/auth/google/callback", params={"code": "auth-code", "state": state})
    assert ok.status_code == 302 and ok.headers["location"].endswith("/")
    assert c.get("/api/auth/me").json()["user"]["email"] == "gina@example.com"
