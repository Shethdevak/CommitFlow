import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

const FIELDS = [
  ["author_name", "AUTHOR_NAME", "text"],
  ["timezone", "TIMEZONE", "text"],
  ["github_token", "GITHUB_TOKEN", "password"],
  ["gitlab_token", "GITLAB_TOKEN", "password"],
  ["gitlab_api_url", "GITLAB_API_URL", "text"],
  ["redmine_url", "REDMINE_URL", "text"],
  ["redmine_api_key", "REDMINE_API_KEY", "password"],
  ["ai_provider", "AI_PROVIDER", "text"],
  ["groq_api_key", "GROQ_API_KEY", "password"],
  ["openai_api_key", "OPENAI_API_KEY", "password"],
  ["daily_hour_goal", "DAILY_HOUR_GOAL", "number"],
  ["min_todos", "MIN_TODOS", "number"],
  ["project_match_threshold", "PROJECT_MATCH_THRESHOLD", "number"],
];

export default function SettingsPage() {
  const { token } = useAuth();
  const [form, setForm] = useState({});
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/api/settings", { token })
      .then((data) => {
        const next = { ...data };
        // Don't put masked secrets back into password fields as real values
        for (const key of [
          "github_token",
          "gitlab_token",
          "redmine_api_key",
          "groq_api_key",
          "openai_api_key",
          "gemini_api_key",
          "anthropic_api_key",
          "openrouter_api_key",
        ]) {
          next[key] = "";
        }
        setForm(next);
      })
      .catch((e) => setError(e.message));
  }, [token]);

  function setField(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSave(e) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    setError("");
    try {
      const body = { ...form };
      // Omit empty secrets so we keep existing encrypted values
      for (const key of Object.keys(body)) {
        if (
          ["github_token", "gitlab_token", "redmine_api_key", "groq_api_key", "openai_api_key"].includes(key) &&
          (!body[key] || !String(body[key]).trim())
        ) {
          delete body[key];
        }
      }
      if (body.daily_hour_goal != null) body.daily_hour_goal = Number(body.daily_hour_goal);
      if (body.min_todos != null) body.min_todos = Number(body.min_todos);
      if (body.project_match_threshold != null) {
        body.project_match_threshold = Number(body.project_match_threshold);
      }
      const saved = await api("/api/settings", { method: "PUT", token, body });
      setMsg("Settings saved.");
      const next = { ...saved };
      for (const key of ["github_token", "gitlab_token", "redmine_api_key", "groq_api_key", "openai_api_key"]) {
        next[key] = "";
      }
      setForm(next);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <h1>Your integrations</h1>
      <p className="lede">Same values as your CLI `.env` — stored encrypted per user.</p>
      <form className="settings-grid" onSubmit={onSave}>
        {FIELDS.map(([key, label, type]) => (
          <label key={key}>
            {label}
            <input
              type={type}
              value={form[key] ?? ""}
              placeholder={type === "password" ? (form[`has_${key}`] ? "•••• saved — leave blank to keep" : "") : ""}
              onChange={(e) => setField(key, e.target.value)}
            />
          </label>
        ))}
        <label className="full">
          Optional repo mappings YAML
          <textarea
            rows={8}
            value={form.mappings_yaml || ""}
            onChange={(e) => setField("mappings_yaml", e.target.value)}
            placeholder={"repositories:\n  org/repo:\n    redmine_project: My Project\n    provider: github"}
          />
        </label>
        {msg && <p className="ok full">{msg}</p>}
        {error && <p className="error full">{error}</p>}
        <button type="submit" className="full" disabled={busy}>
          {busy ? "Saving…" : "Save settings"}
        </button>
      </form>
    </div>
  );
}
