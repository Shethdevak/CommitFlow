import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

export default function SyncPage() {
  const { token } = useAuth();
  const [dryRun, setDryRun] = useState(true);
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!confirmOpen) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape" && !committing) setConfirmOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmOpen, committing]);

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const data = await api("/api/sync", {
        method: "POST",
        token,
        body: { dry_run: dryRun, today: !date, date: date || null },
      });
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function openCommitConfirm() {
    if (!result?.planned_todos?.length) return;
    setConfirmOpen(true);
  }

  async function confirmCommit() {
    if (!result?.planned_todos?.length) return;

    setCommitting(true);
    setError("");
    try {
      const data = await api("/api/sync/commit", {
        method: "POST",
        token,
        body: { date: result.date, planned_todos: result.planned_todos },
      });
      setResult(data);
      setConfirmOpen(false);
    } catch (err) {
      setError(err.message);
      setConfirmOpen(false);
    } finally {
      setCommitting(false);
    }
  }

  const canCommit = result?.dry_run && result?.planned_todos?.length > 0 && !busy && !committing;
  const maxHours = result?.planned_todos?.length
    ? Math.max(...result.planned_todos.map((t) => t.hours))
    : 1;

  return (
    <div className="page-block reveal">
      <header className="page-intro">
        <h1>Sync desk</h1>
        <p>
          Scan commits, weight the day, preview the plan — then commit those exact to-dos to Redmine
          without running the cycle twice.
        </p>
      </header>

      <section className="control-strip">
        <label className="field compact">
          <span>Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>

        <label className="toggle">
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          <span className="toggle-ui" aria-hidden="true" />
          <span className="toggle-label">Dry run only</span>
        </label>

        <div className="control-actions">
          <button type="button" className="btn-primary" onClick={run} disabled={busy || committing}>
            {busy ? "Scanning…" : dryRun ? "Preview plan" : "Sync to Redmine"}
          </button>
          {canCommit && (
            <button type="button" className="btn-accent" onClick={openCommitConfirm} disabled={committing}>
              Commit all
            </button>
          )}
        </div>
      </section>

      {error && <p className="banner-error">{error}</p>}

      {result && (
        <section className="result-stage reveal">
          <div className="metric-row">
            <article>
              <p className="metric-label">Commits</p>
              <p className="metric-value">{result.processed_commits_count}</p>
            </article>
            <article>
              <p className="metric-label">To-dos</p>
              <p className="metric-value">{result.todos_planned}</p>
            </article>
            <article>
              <p className="metric-label">Hours</p>
              <p className="metric-value">{result.hours_logged}</p>
            </article>
            <article>
              <p className="metric-label">Mode</p>
              <p className={`metric-value mode ${result.dry_run ? "preview" : "live"}`}>
                {result.dry_run ? "Preview" : "Written"}
              </p>
            </article>
          </div>

          {result.dry_run && result.planned_todos?.length > 0 && (
            <div className="commit-callout">
              <div>
                <h3>Ready to write {result.date}?</h3>
                <p>
                  This keeps your weighted plan as-is — no second Git scan, no second AI pass.
                </p>
              </div>
              <button type="button" className="btn-accent" onClick={openCommitConfirm} disabled={committing}>
                Commit all to Redmine
              </button>
            </div>
          )}

          {!result.dry_run && (
            <p className="banner-ok">
              Redmine updated — created {result.created_issues?.length || 0}, updated{" "}
              {result.updated_issues?.length || 0}, time entries {result.time_entries_created}.
            </p>
          )}

          {result.errors?.length > 0 && (
            <div className="note-box">
              <h3>Notes</h3>
              <ul>
                {result.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="plan-list">
            <div className="plan-head">
              <h2>Day plan</h2>
              <p>Bar width reflects relative hours in this plan.</p>
            </div>
            <ol>
              {result.planned_todos.map((t, i) => (
                <li key={`${t.subject}-${i}`} className="plan-row" style={{ "--i": i }}>
                  <div className="plan-index">{String(i + 1).padStart(2, "0")}</div>
                  <div className="plan-body">
                    <div className="plan-topline">
                      <p className="plan-subject">{t.subject}</p>
                      <p className="plan-hours">{t.hours}h</p>
                    </div>
                    <div className="plan-meta">
                      <span>{t.project_name}</span>
                      <span>{t.feature_name}</span>
                      <span className={t.is_synthetic ? "chip soft" : "chip"}>
                        {t.is_synthetic ? "support" : "commit"}
                      </span>
                    </div>
                    <div className="plan-bar" aria-hidden="true">
                      <span style={{ width: `${Math.max(8, (t.hours / maxHours) * 100)}%` }} />
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </div>

          {result.unmapped_repos?.length > 0 && (
            <p className="fineprint">Unmapped repos: {result.unmapped_repos.join(", ")}</p>
          )}
        </section>
      )}

      {confirmOpen && result && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => !committing && setConfirmOpen(false)}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="commit-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="modal-kicker">Write to Redmine</p>
            <h2 id="commit-modal-title">Commit this day plan?</h2>
            <p className="modal-copy">
              You&apos;re about to create to-dos and log spent time. This uses the preview you already
              approved — no re-scan.
            </p>

            <div className="modal-stats">
              <div>
                <span>Date</span>
                <strong>{result.date}</strong>
              </div>
              <div>
                <span>To-dos</span>
                <strong>{result.planned_todos.length}</strong>
              </div>
              <div>
                <span>Hours</span>
                <strong>{result.hours_logged}h</strong>
              </div>
            </div>

            <ul className="modal-preview">
              {result.planned_todos.slice(0, 4).map((t, i) => (
                <li key={`${t.subject}-${i}`}>
                  <span>{t.hours}h</span>
                  <p>{t.subject}</p>
                </li>
              ))}
              {result.planned_todos.length > 4 && (
                <li className="more">+{result.planned_todos.length - 4} more</li>
              )}
            </ul>

            <div className="modal-actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setConfirmOpen(false)}
                disabled={committing}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-accent"
                onClick={confirmCommit}
                disabled={committing}
              >
                {committing ? "Writing…" : "Yes, write to Redmine"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
