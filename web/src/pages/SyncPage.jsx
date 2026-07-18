import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { loadSyncDeskState, saveSyncDeskState } from "../syncDeskState";

function sumHours(todos) {
  return Math.round(todos.reduce((s, t) => s + (Number(t.hours) || 0), 0) * 100) / 100;
}

function stampTodos(todos) {
  return (todos || []).map((t, i) => ({
    ...t,
    hours: Number(t.hours) || 0,
    _uid: t._uid || `todo-${i}-${String(t.subject || "").slice(0, 40)}`,
  }));
}

function stripClientFields(todos) {
  return todos.map(({ _uid, ...rest }) => rest);
}

function normalizeResult(data) {
  const planned = stampTodos(data.planned_todos || []);
  return {
    ...data,
    planned_todos: planned,
    todos_planned: planned.length,
    hours_logged: sumHours(planned),
  };
}

export default function SyncPage() {
  const initial = loadSyncDeskState();
  const [dryRun, setDryRun] = useState(() => initial?.dryRun ?? true);
  const [date, setDate] = useState(() => initial?.date ?? "");
  const [busy, setBusy] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState(() => initial?.error ?? "");
  const [result, setResult] = useState(() =>
    initial?.result ? normalizeResult(initial.result) : null
  );
  const [selected, setSelected] = useState(() => {
    const todos = initial?.result?.planned_todos || [];
    return new Set(stampTodos(todos).map((t) => t._uid));
  });

  useEffect(() => {
    saveSyncDeskState({ date, dryRun, result, error });
  }, [date, dryRun, result, error]);

  useEffect(() => {
    if (!confirmOpen) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape" && !committing) setConfirmOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmOpen, committing]);

  const todos = result?.planned_todos || [];
  const selectedTodos = useMemo(
    () => todos.filter((t) => selected.has(t._uid)),
    [todos, selected]
  );
  const selectedHours = sumHours(selectedTodos);
  const editable = Boolean(result?.dry_run && todos.length > 0);
  const canCommit = editable && selectedTodos.length > 0 && !busy && !committing;
  const maxHours = todos.length ? Math.max(...todos.map((t) => Number(t.hours) || 0), 0.25) : 1;

  function updateTodos(nextTodos) {
    setResult((prev) => {
      if (!prev) return prev;
      const planned = stampTodos(nextTodos);
      return {
        ...prev,
        planned_todos: planned,
        todos_planned: planned.length,
        hours_logged: sumHours(planned),
      };
    });
    setSelected((prev) => {
      const ids = new Set(stampTodos(nextTodos).map((t) => t._uid));
      return new Set([...prev].filter((id) => ids.has(id)));
    });
  }

  function setHours(uid, raw) {
    const hours = Math.max(0, Math.min(24, Number(raw) || 0));
    updateTodos(todos.map((t) => (t._uid === uid ? { ...t, hours } : t)));
  }

  function removeTodo(uid) {
    updateTodos(todos.filter((t) => t._uid !== uid));
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(uid);
      return next;
    });
  }

  function toggleSelected(uid) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(todos.map((t) => t._uid)));
  }

  function selectNone() {
    setSelected(new Set());
  }

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    setSelected(new Set());
    try {
      const data = await api("/api/sync", {
        method: "POST",
        body: { dry_run: dryRun, today: !date, date: date || null },
      });
      const normalized = normalizeResult(data);
      setResult(normalized);
      setSelected(new Set(normalized.planned_todos.map((t) => t._uid)));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function openCommitConfirm() {
    if (!canCommit) return;
    setConfirmOpen(true);
  }

  async function confirmCommit() {
    if (!canCommit || !result) return;

    setCommitting(true);
    setError("");
    try {
      const data = await api("/api/sync/commit", {
        method: "POST",
        body: {
          date: result.date,
          planned_todos: stripClientFields(selectedTodos),
        },
      });
      setResult(normalizeResult(data));
      setSelected(new Set());
      setConfirmOpen(false);
    } catch (err) {
      setError(err.message);
      setConfirmOpen(false);
    } finally {
      setCommitting(false);
    }
  }

  return (
    <div className="page-block reveal">
      <header className="page-intro">
        <h1>Sync desk</h1>
        <p>
          Scan commits, weight the day, preview the plan — edit hours or drop to-dos, then commit
          only what you select.
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
              Commit selected ({selectedTodos.length})
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

          {editable && (
            <div className="commit-callout">
              <div>
                <h3>Edit, then write {result.date}</h3>
                <p>
                  Change hours, remove rows you don’t want, and commit only the checked to-dos —
                  {selectedTodos.length} selected · {selectedHours}h.
                </p>
              </div>
              <button type="button" className="btn-accent" onClick={openCommitConfirm} disabled={!canCommit}>
                Commit selected
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
              <div>
                <h2>Day plan</h2>
                <p>
                  {editable
                    ? "Tick what to commit. Edit hours or remove a row — then move time into another."
                    : result.date
                      ? `Plan for ${result.date}`
                      : "Bar width reflects relative hours in this plan."}
                </p>
              </div>
              {editable && (
                <div className="plan-head-actions">
                  <button type="button" className="text-switch" onClick={selectAll}>
                    Select all
                  </button>
                  <button type="button" className="text-switch" onClick={selectNone}>
                    Select none
                  </button>
                </div>
              )}
            </div>
            <ol>
              {todos.map((t, i) => (
                <li
                  key={t._uid}
                  className={`plan-row ${editable ? "is-editable" : ""} ${
                    editable && !selected.has(t._uid) ? "is-deselected" : ""
                  }`}
                  style={{ "--i": i }}
                >
                  {editable ? (
                    <label className="plan-check">
                      <input
                        type="checkbox"
                        checked={selected.has(t._uid)}
                        onChange={() => toggleSelected(t._uid)}
                        aria-label={`Include “${t.subject}” in commit`}
                      />
                    </label>
                  ) : (
                    <div className="plan-index">{String(i + 1).padStart(2, "0")}</div>
                  )}
                  <div className="plan-body">
                    <div className="plan-topline">
                      <p className="plan-subject">{t.subject}</p>
                      {editable ? (
                        <label className="plan-hours-edit">
                          <input
                            type="number"
                            min="0"
                            max="24"
                            step="0.25"
                            value={t.hours}
                            onChange={(e) => setHours(t._uid, e.target.value)}
                            aria-label={`Hours for “${t.subject}”`}
                          />
                          <span>h</span>
                        </label>
                      ) : (
                        <p className="plan-hours">{t.hours}h</p>
                      )}
                    </div>
                    <div className="plan-meta">
                      <span>{t.project_name}</span>
                      <span>{t.feature_name}</span>
                      <span className={t.is_synthetic ? "chip soft" : "chip"}>
                        {t.is_synthetic ? "support" : "commit"}
                      </span>
                      {editable && (
                        <button
                          type="button"
                          className="plan-remove"
                          onClick={() => removeTodo(t._uid)}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                    <div className="plan-bar" aria-hidden="true">
                      <span style={{ width: `${Math.max(8, (t.hours / maxHours) * 100)}%` }} />
                    </div>
                  </div>
                </li>
              ))}
            </ol>
            {editable && todos.length === 0 && (
              <p className="plan-empty">No to-dos left in this plan. Run Preview again to rebuild.</p>
            )}
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
            <h2 id="commit-modal-title">Commit selected to-dos?</h2>
            <p className="modal-copy">
              Only the checked items (with your edited hours) will be written. Unchecked rows stay
              out of Redmine.
            </p>

            <div className="modal-stats">
              <div>
                <span>Date</span>
                <strong>{result.date}</strong>
              </div>
              <div>
                <span>To-dos</span>
                <strong>{selectedTodos.length}</strong>
              </div>
              <div>
                <span>Hours</span>
                <strong>{selectedHours}h</strong>
              </div>
            </div>

            <ul className="modal-preview">
              {selectedTodos.slice(0, 4).map((t) => (
                <li key={t._uid}>
                  <span>{t.hours}h</span>
                  <p>{t.subject}</p>
                </li>
              ))}
              {selectedTodos.length > 4 && (
                <li className="more">+{selectedTodos.length - 4} more</li>
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
                disabled={committing || selectedTodos.length === 0}
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
