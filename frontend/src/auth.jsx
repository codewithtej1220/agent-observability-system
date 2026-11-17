import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ loading: true, me: null });

  const refresh = useCallback(async () => {
    try {
      const me = await api("/api/auth/me");
      setState({ loading: false, me });
    } catch {
      setState({ loading: false, me: null });
    }
  }, []);

  useEffect(() => {
    refresh();
    const onUnauthorized = () => setState((s) => (s.me ? { loading: false, me: null } : s));
    window.addEventListener("aobs:unauthorized", onUnauthorized);
    return () => window.removeEventListener("aobs:unauthorized", onUnauthorized);
  }, [refresh]);

  const logout = async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* already signed out */ }
    setState({ loading: false, me: null });
  };

  const switchWorkspace = async (id) => {
    await api("/api/auth/switch-workspace", { method: "POST", body: { workspace_id: Number(id) } });
    // Every page's data is workspace-scoped: reload cleanly.
    window.location.assign("/");
  };

  const me = state.me;
  return (
    <AuthContext.Provider value={{
      loading: state.loading, me, user: me?.user, workspace: me?.workspace, workspaces: me?.workspaces || [],
      role: me?.workspace?.role, can: (r) => ({ viewer: 0, member: 1, admin: 2 })[me?.workspace?.role] >= ({ viewer: 0, member: 1, admin: 2 })[r],
      refresh, logout, switchWorkspace,
    }}>
      {children}
    </AuthContext.Provider>
  );
}
