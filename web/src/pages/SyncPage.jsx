import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

export default function SyncPage() {
  const { token } = useAuth();
  const [dryRun, setDryRun] = useState(true);
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const body = {
        dry_run: dryRun,
        today: !date,
        date: date || null,
      };
      const data = await api("/api/sync", { method: "POST", token, body });
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function commitAll() {
    if (!result?.planned_todos?.length) return;
    const ok = window.confirm(
      `Write ${result.planned_todos.length} to-dos (${result.hours_logged}h) to Redmine for ${result.date}?`
    );
    if (!ok) return;

    setCommitting(true);
    setError("");
    try {
      const data = await api("/api/sync/commit", {
        method: "POST",
        token,
        body: {
          date: result.date,
          planned_todos: result.planned_todos,
        },
      });
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setCommitting(false);
    }
  }

  const canCommit =
    result?.dry_run &&
    result?.planned_todos?.length > 0 &&
    !busy &&
    !committing;

  return (
    <div className="page">
      <h1>Sync</h1>
      <p className="lede">
        Same engine as the CLI. Preview with dry-run, then <strong>Commit all</strong> to write
        those exact to-dos to Redmine — no second fetch cycle.
      </p>

      <div className="sync-controls">
        <label>
          Date (optional)
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="check">
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          Dry run (no Redmine write)
        </label>
        <button type="button" onClick={run} disabled={busy || committing}>
          {busy ? "Running…" : dryRun ? "Preview today" : "Sync for real"}
        </button>
        {canCommit && (
          <button type="button" className="commit-btn" onClick={commitAll} disabled={committing}>
            {committing ? "Committing…" : "Commit all to Redmine"}
          </button>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <section className="results">
          <div className="stats">
            <div>
              <strong>{result.processed_commits_count}</strong>
              <span>commits</span>
            </div>
            <div>
              <strong>{result.todos_planned}</strong>
              <span>to-dos</span>
            </div>
            <div>
              <strong>{result.hours_logged}h</strong>
              <span>hours</span>
            </div>
            <div>
              <strong>{result.dry_run ? "dry-run" : "written"}</strong>
              <span>mode</span>
            </div>
          </div>

          {result.dry_run && result.planned_todos?.length > 0 && (
            <div className="commit-banner">
              <p>Preview looks good? Write these exact to-dos to Redmine without re-scanning Git.</p>
              <button type="button" className="commit-btn" onClick={commitAll} disabled={committing}>
                {committing ? "Committing…" : "Commit all to Redmine"}
              </button>
            </div>
          )}

          {!result.dry_run && (
            <p className="ok">
              Written to Redmine — created {result.created_issues?.length || 0}, updated{" "}
              {result.updated_issues?.length || 0}, time entries {result.time_entries_created}.
            </p>
          )}

          {result.errors?.length > 0 && (
            <div className="warn-box">
              <h3>Notes / errors</h3>
              <ul>
                {result.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Hours</th>
                <th>Project</th>
                <th>Feature</th>
                <th>Subject</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody>
              {result.planned_todos.map((t, i) => (
                <tr key={`${t.subject}-${i}`}>
                  <td>{i + 1}</td>
                  <td>{t.hours}h</td>
                  <td>{t.project_name}</td>
                  <td>{t.feature_name}</td>
                  <td>{t.subject}</td>
                  <td>{t.is_synthetic ? "synthetic" : "commit"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {result.unmapped_repos?.length > 0 && (
            <p className="muted">Unmapped repos: {result.unmapped_repos.join(", ")}</p>
          )}
        </section>
      )}
    </div>
  );
}
