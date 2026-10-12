import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, useApi } from "../api";
import { useAuth } from "../auth";

function GoogleButton() {
  return (
    <a className="btn google-btn" href="/api/auth/google/login">
      <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
        <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
        <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
        <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
        <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
      </svg>
      Continue with Google
    </a>
  );
}

export function AuthPage({ mode }) {
  const signup = mode === "signup";
  const config = useApi("/api/auth/config");
  const { refresh } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState(params.get("error"));
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(signup ? "/api/auth/signup" : "/api/auth/login", {
        method: "POST", body: signup ? form : { email: form.email, password: form.password },
      });
      await refresh();
      nav("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="brand-title" style={{ color: "var(--text)", fontSize: 18 }}>Agent Observability</div>
        <div className="muted small" style={{ marginBottom: 18 }}>Monitor every LLM and agent your team runs</div>
        <h1 style={{ marginBottom: 14 }}>{signup ? "Create your account" : "Sign in"}</h1>
        {config.data?.google_enabled && (
          <>
            <GoogleButton />
            <div className="divider"><span>or</span></div>
          </>
        )}
        <form onSubmit={submit} className="stack" style={{ gap: 12 }}>
          {signup && (
            <label className="field">Name
              <input type="text" value={form.name} onChange={set("name")} autoComplete="name" />
            </label>
          )}
          <label className="field">Email
            <input type="email" required value={form.email} onChange={set("email")} autoComplete="email" />
          </label>
          <label className="field">Password
            <input type="password" required minLength={signup ? 8 : undefined} value={form.password} onChange={set("password")}
                   autoComplete={signup ? "new-password" : "current-password"} />
            {signup && <span className="muted">At least 8 characters, with letters and numbers or symbols.</span>}
          </label>
          {error && <div className="error-box small">{error}</div>}
          <button className="primary" type="submit" disabled={busy}>{busy ? "Please wait…" : signup ? "Create account" : "Sign in"}</button>
        </form>
        <div className="small text-2" style={{ marginTop: 16 }}>
          {signup ? <>Already have an account? <Link to="/login">Sign in</Link></> : <>New here? <Link to="/signup">Create an account</Link></>}
        </div>
      </div>
    </div>
  );
}
