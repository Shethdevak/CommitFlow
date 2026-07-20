import { useEffect, useState } from "react";
import { api } from "../api";
import SecretField from "../components/SecretField.jsx";

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
      ["github_token", "GITHUB_TOKEN", "secret", "ghp_…"],
      ["gitlab_token", "GITLAB_TOKEN", "secret", "glpat-…"],
      ["gitlab_api_url", "GITLAB_API_URL", "url", "https://git.example.com"],
    ],
  },
  {
    id: "redmine",
    title: "Redmine",
    blurb: "Where to-dos and spent time land.",
    fields: [
      ["redmine_url", "REDMINE_URL", "url", "https://redmine.example.com"],
      ["redmine_api_key", "REDMINE_API_KEY", "secret", "api key"],
    ],
  },
  {
    id: "ai",
    title: "AI classifier",
    blurb: "Maps commits onto existing Redmine features.",
    fields: [
      ["ai_provider", "AI_PROVIDER", "text", "groq"],
      ["groq_api_key", "GROQ_API_KEY", "secret", "gsk_…"],
      ["openai_api_key", "OPENAI_API_KEY", "secret", "sk-…"],
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

const HAS_KEY = {
  github_token: "has_github_token",
  gitlab_token: "has_gitlab_token",
  redmine_api_key: "has_redmine_api_key",
  groq_api_key: "has_groq_api_key",
  openai_api_key: "has_openai_api_key",
};

function isMaskedSecret(value) {
  if (!value) return false;
  const s = String(value);
  return s.includes("…") || s.includes("...") || s === "********";
}

function secretIsSaved(form, key) {
  const flag = HAS_KEY[key];
  if (flag && form[flag]) return true;
  return Boolean(form[key] && isMaskedSecret(form[key]));
}

function normalizeSettings(data) {
  const next = { ...data };
  for (const key of SECRET_KEYS) {
    // Keep masked preview from API so the user can see what's stored
    if (next[key] == null) next[key] = "";
  }
  return next;
}

function PlainField({ label, type, value, placeholder, onChange }) {
  return (
    <label className="field settings-field">
      <span className="field-label-row">
        <span>{label}</span>
        <span className="field-badge-slot" aria-hidden="true" />
      </span>
      <input
        type={type === "url" ? "url" : type}
        value={value ?? ""}
        placeholder={placeholder}
        spellCheck={false}
        onChange={onChange}
      />
      <span className="field-hint is-empty">{"\u00a0"}</span>
    </label>
  );
}

export default function SettingsPage() {
  const [form, setForm] = useState({});
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/api/settings")
      .then((data) => setForm(normalizeSettings(data)))
      .catch((e) => setError(e.message));
  }, []);

  function setField(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function onSecretFocus(key) {
    setForm((f) => {
      if (!isMaskedSecret(f[key])) return f;
      return { ...f, [key]: "" };
    });
  }

  async function onSave(e) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    setError("");
    try {
      const body = { ...form };
      for (const key of SECRET_KEYS) {
        const value = body[key];
        // Don't overwrite stored secrets with empty or masked placeholders
        if (!value || !String(value).trim() || isMaskedSecret(value)) {
          delete body[key];
        }
      }
      delete body.has_github_token;
      delete body.has_gitlab_token;
      delete body.has_redmine_api_key;
      delete body.has_groq_api_key;
      delete body.has_openai_api_key;

      if (body.daily_hour_goal != null) body.daily_hour_goal = Number(body.daily_hour_goal);
      if (body.min_todos != null) body.min_todos = Number(body.min_todos);
      if (body.project_match_threshold != null) {
        body.project_match_threshold = Number(body.project_match_threshold);
      }
      const saved = await api("/api/settings", { method: "PUT", body });
      setMsg("Integrations saved.");
      setForm(normalizeSettings(saved));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const checklist = [
    ["GitHub token", secretIsSaved(form, "github_token")],
    ["GitLab token", secretIsSaved(form, "gitlab_token")],
    ["Redmine URL", Boolean(form.redmine_url)],
    ["Redmine API key", secretIsSaved(form, "redmine_api_key")],
    ["Groq API key", secretIsSaved(form, "groq_api_key")],
  ];

  return (
    <div className="page-block reveal">
      <header className="page-intro">
        <h1>Integrations</h1>
        <p>Same knobs as your CLI `.env` — scoped to your account, encrypted at rest.</p>
      </header>

      <div className="settings-status">
        <p className="settings-status-title">Stored credentials</p>
        <ul className="settings-status-list">
          {checklist.map(([label, ok]) => (
            <li key={label} className={ok ? "is-ok" : "is-missing"}>
              <span className="status-dot" aria-hidden="true" />
              <span>
                {label}: <strong>{ok ? "saved" : "not set"}</strong>
              </span>
            </li>
          ))}
        </ul>
        <p className="fineprint">
          Tokens and API keys stay masked. Use the eye only on those fields to peek at what you type.
          Focus a secret to replace it — full keys are never shown again after save. URLs stay plain
          text.
        </p>
      </div>

      <form className="settings-form" onSubmit={onSave}>
        {SECTIONS.map((section) => (
          <section key={section.id} className="settings-section">
            <div className="section-copy">
              <h2>{section.title}</h2>
              <p>{section.blurb}</p>
            </div>
            <div className="section-fields">
              {section.fields.map(([key, label, type, placeholder]) => {
                if (type === "secret") {
                  const saved = secretIsSaved(form, key);
                  return (
                    <SecretField
                      key={key}
                      layout="settings"
                      label={label}
                      value={form[key] ?? ""}
                      placeholder={saved ? "Saved — focus to replace" : placeholder}
                      badge={
                        <span className={`secret-badge ${saved ? "saved" : "missing"}`}>
                          {saved ? "Saved in account" : "Not set"}
                        </span>
                      }
                      hint={
                        saved && isMaskedSecret(form[key])
                          ? `Stored value: ${form[key]}`
                          : undefined
                      }
                      onFocus={() => onSecretFocus(key)}
                      onChange={(e) => setField(key, e.target.value)}
                    />
                  );
                }
                return (
                  <PlainField
                    key={key}
                    label={label}
                    type={type}
                    value={form[key] ?? ""}
                    placeholder={placeholder}
                    onChange={(e) => setField(key, e.target.value)}
                  />
                );
              })}
            </div>
          </section>
        ))}

        <section className="settings-section">
          <div className="section-copy">
            <h2>Repo mappings</h2>
            <p>Optional YAML overrides when fuzzy project matching isn’t enough.</p>
          </div>
          <div className="section-fields">
            <label className="field settings-field full">
              <span className="field-label-row">
                <span>MAPPINGS_YAML</span>
                <span className="field-badge-slot" aria-hidden="true" />
              </span>
              <textarea
                rows={9}
                value={form.mappings_yaml || ""}
                onChange={(e) => setField("mappings_yaml", e.target.value)}
                placeholder={
                  "repositories:\n  org/repo:\n    redmine_project: My Project\n    provider: github"
                }
              />
              <span className="field-hint is-empty">{"\u00a0"}</span>
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
