import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function AuthCallback() {
  const { refreshUser } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const user = await refreshUser();
      if (cancelled) return;
      navigate(user ? "/" : "/login", { replace: true });
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshUser, navigate]);

  return <div className="center">Signing you in…</div>;
}
