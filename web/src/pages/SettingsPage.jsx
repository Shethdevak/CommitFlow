import { useEffect, useState } from "react";
import { api } from "../api";

const SECTIONS = [
  {
    id: "identity",
    title: "Identity",
    blurb: "How we match your commits.",
    fields: [
      ["author_name", "AUTHOR_NAME", "text", "Git author / GitHub login"],
      ["timezone", "TIMEZONE", "text", "Asia/Kolkata"],
    ],
  },
  {
    id: "git",
    title: "Git sources",
    blurb: "Tokens stay encrypted. Leave blank to keep a saved value.",
    fields: [
      ["github_token", "GITHUB_TOKEN", "password", "ghp_…"],
      ["gitlab_token", "GITLAB_TOKEN", "password", "glpat-…"],
      ["gitlab_api_url", "GITLAB_API_URL", "text", "https://git.example.com"],
    ],
  },
  {
    id: "redmine",
    title: "Redmine",
    blurb: "Where to-dos and spent time land.",
    fields: [
      ["redmine_url", "REDMINE_URL", "text", "https://redmine.example.com"],
      ["redmine_api_key", "REDMINE_API_KEY", "password", "api key"],
    ],
  },
  {
    id: "ai",
    title: "AI classifier",
    blurb: "Maps commits onto existing Redmine features.",
    fields: [
      ["ai_provider", "AI_PROVIDER", "text", "groq"],
      ["groq_api_key", "GROQ_API_KEY", "password", "gsk_…"],
      ["openai_api_key", "OPENAI_API_KEY", "password", "sk-…"],
    ],
  },
  {
    id: "goals",
    title: "Day shape",
    blurb: "How the 8-hour plan is built.",
    fields: [
      ["daily_hour_goal", "DAILY_HOUR_GOAL", "number", "8"],
      ["min_todos", "MIN_TODOS", "number", "3"],
      ["project_match_threshold", "PROJECT_MATCH_THRESHOLD", "number", "70"],
    ],
  },
];

const SECRET_KEYS = [
  "github_token",
  "gitlab_token",
  "redmine_api_key",
  "groq_api_key",
  "openai_api_key",
  "gemini_api_key",
  "anthropic_api_key",
  "openrouter_api_key",
];

export default function SettingsPage() {
  const [form, setForm] = useState({});
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/api/settings")
      .then((data) => {
        const next = { ...data };
        for (const key of SECRET_KEYS) next[key] = "";
        setForm(next);
      })
      .catch((e) => setError(e.message));
  }, []);

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
      for (const key of SECRET_KEYS) {
        if (!body[key] || !String(body[key]).trim()) delete body[key];
      }
      if (body.daily_hour_goal != null) body.daily_hour_goal = Number(body.daily_hour_goal);
      if (body.min_todos != null) body.min_todos = Number(body.min_todos);
      if (body.project_match_threshold != null) {
        body.project_match_threshold = Number(body.project_match_threshold);
      }
      const saved = await api("/api/settings", { method: "PUT", body });
      setMsg("Integrations saved.");
      const next = { ...saved };
      for (const key of SECRET_KEYS) next[key] = "";
      setForm(next);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-block reveal">
      <header className="page-intro">
        <h1>Integrations</h1>
        <p>Same knobs as your CLI `.env` — scoped to your account, encrypted at rest.</p>
      </header>

      <form className="settings-form" onSubmit={onSave}>
        {SECTIONS.map((section) => (
          <section key={section.id} className="settings-section">
            <div className="section-copy">
              <h2>{section.title}</h2>
              <p>{section.blurb}</p>
            </div>
            <div className="section-fields">
              {section.fields.map(([key, label, type, placeholder]) => (
                <label key={key} className="field">
                  <span>{label}</span>
                  <input
                    type={type}
                    value={form[key] ?? ""}
                    placeholder={
                      type === "password" && form[`has_${key}`]
                        ? "Saved — leave blank to keep"
                        : placeholder
                    }
                    onChange={(e) => setField(key, e.target.value)}
                  />
                </label>
              ))}
            </div>
          </section>
        ))}

        <section className="settings-section">
          <div className="section-copy">
            <h2>Repo mappings</h2>
            <p>Optional YAML overrides when fuzzy project matching isn’t enough.</p>
          </div>
          <div className="section-fields">
            <label className="field full">
              <span>MAPPINGS_YAML</span>
              <textarea
                rows={9}
                value={form.mappings_yaml || ""}
                onChange={(e) => setField("mappings_yaml", e.target.value)}
                placeholder={"repositories:\n  org/repo:\n    redmine_project: My Project\n    provider: github"}
              />
            </label>
          </div>
        </section>

        <div className="form-actions">
          {msg && <p className="banner-ok">{msg}</p>}
          {error && <p className="banner-error">{error}</p>}
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Save integrations"}
          </button>
        </div>
      </form>
    </div>
  );
}
