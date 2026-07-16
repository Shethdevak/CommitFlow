import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function AuthCallback() {
  const { acceptToken } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "");
    const params = new URLSearchParams(hash);
    const access = params.get("access_token");
    if (access) {
      acceptToken(access);
      navigate("/", { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  }, [acceptToken, navigate]);

  return <div className="center">Signing you in…</div>;
}
