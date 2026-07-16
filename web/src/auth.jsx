import React, { createContext, useContext, useMemo, useState, useEffect } from "react";
import { api } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("cf_token") || "");
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!token);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    api("/api/auth/me", { token })
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("cf_token");
        setToken("");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [token]);

  const value = useMemo(
    () => ({
      token,
      user,
      loading,
      async login(email, password) {
        const data = await api("/api/auth/login", { method: "POST", body: { email, password } });
        localStorage.setItem("cf_token", data.access_token);
        setToken(data.access_token);
        setUser(data.user);
      },
      async register(email, password, display_name) {
        const data = await api("/api/auth/register", {
          method: "POST",
          body: { email, password, display_name },
        });
        localStorage.setItem("cf_token", data.access_token);
        setToken(data.access_token);
        setUser(data.user);
      },
      acceptToken(accessToken) {
        localStorage.setItem("cf_token", accessToken);
        setToken(accessToken);
      },
      logout() {
        localStorage.removeItem("cf_token");
        setToken("");
        setUser(null);
      },
    }),
    [token, user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
