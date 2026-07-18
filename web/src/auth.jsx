import React, { createContext, useContext, useMemo, useState, useEffect, useCallback } from "react";
import { api } from "./api";
import { clearSyncDeskState } from "./syncDeskState";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    try {
      const me = await api("/api/auth/me");
      setUser(me);
      return me;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.removeItem("cf_token");
    } catch {
      /* ignore */
    }
    loadUser().finally(() => setLoading(false));
  }, [loadUser]);

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: !!user,
      async login(email, password) {
        const data = await api("/api/auth/login", { method: "POST", body: { email, password } });
        setUser(data.user);
      },
      async register(email, password, display_name) {
        const data = await api("/api/auth/register", {
          method: "POST",
          body: { email, password, display_name },
        });
        setUser(data.user);
      },
      async refreshUser() {
        setLoading(true);
        try {
          return await loadUser();
        } finally {
          setLoading(false);
        }
      },
      async logout() {
        try {
          await api("/api/auth/logout", { method: "POST" });
        } catch {
          /* still clear local session */
        }
        clearSyncDeskState();
        setUser(null);
      },
    }),
    [user, loading, loadUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
