import React, { createContext, useContext, useMemo, useState, useEffect, useCallback } from "react";
import { api } from "./api";
import { clearSyncDeskState } from "./syncDeskState";
import { clearDayLogState } from "./dayLogState";

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
      async login(email, password, remember_me = false) {
        const data = await api("/api/auth/login", {
          method: "POST",
          body: { email, password, remember_me },
        });
        setUser(data.user);
      },
      async register(email, password, display_name, remember_me = false) {
        // No session until email is verified — returns verification meta
        return api("/api/auth/register", {
          method: "POST",
          body: { email, password, display_name, remember_me },
        });
      },
      async verifyEmail(email, code, remember_me = false) {
        const data = await api("/api/auth/otp/verify", {
          method: "POST",
          body: { email, code, purpose: "signup", remember_me },
        });
        setUser(data.user);
        return data;
      },
      async resendSignupOtp(email) {
        return api("/api/auth/otp/send", {
          method: "POST",
          body: { email, purpose: "signup" },
        });
      },
      async forgotPassword(email) {
        return api("/api/auth/password/forgot", {
          method: "POST",
          body: { email },
        });
      },
      async verifyResetCode(email, code) {
        return api("/api/auth/password/verify-code", {
          method: "POST",
          body: { email, code },
        });
      },
      async resetPassword(reset_token, password) {
        return api("/api/auth/password/reset", {
          method: "POST",
          body: { reset_token, password },
        });
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
        clearDayLogState();
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
