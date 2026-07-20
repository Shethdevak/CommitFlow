import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
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
  const [error, setError] = useState(() => initial?.error ?? "");
  const [result, setResult] = useState(() =>
    initial?.result ? normalizeResult(initial.result) : null
  );

  /** @type {null | { type: 'commit-one' | 'commit-all' | 'delete', todo?: object }} */
  const [dialog, setDialog] = useState(null);

  useEffect(() => {
    saveSyncDeskState({ date, dryRun, result, error });
  }, [date, dryRun, result, error]);

  useEffect(() => {
    if (!dialog) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape" && !committing) setDialog(null);
    };
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [dialog, committing]);

  const todos = result?.planned_todos || [];
  const editable = Boolean(result?.dry_run && todos.length > 0);
  const canCommitAll = editable && !busy && !committing;
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
  }

  function setHours(uid, raw) {
    const hours = Math.max(0, Math.min(24, Number(raw) || 0));
    updateTodos(todos.map((t) => (t._uid === uid ? { ...t, hours } : t)));
  }

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    setDialog(null);
    try {
      const data = await api("/api/sync", {
        method: "POST",
        body: { dry_run: dryRun, today: !date, date: date || null },
      });
      setResult(normalizeResult(data));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function writeTodos(todosToWrite) {
    if (!result || !todosToWrite.length) return;

    setCommitting(true);
    setError("");
    try {
      const data = await api("/api/sync/commit", {
        method: "POST",
        body: {
          date: result.date,
          planned_todos: stripClientFields(todosToWrite),
        },
      });
      // Keep remaining uncommitted preview rows when committing one / subset
      const writtenUids = new Set(todosToWrite.map((t) => t._uid));
      const remaining = todos.filter((t) => !writtenUids.has(t._uid));
      if (remaining.length > 0 && data.dry_run === false) {
        setResult({
          ...normalizeResult(data),
          dry_run: true,
          planned_todos: remaining,
          todos_planned: remaining.length,
          hours_logged: sumHours(remaining),
          // Keep a note that a write happened
          errors: [
            ...(data.errors || []),
            `Wrote ${todosToWrite.length} to-do(s) to Redmine. ${remaining.length} still in your plan.`,
          ],
        });
      } else {
        setResult(normalizeResult(data));
      }
      setDialog(null);
    } catch (err) {
      setError(err.message);
      setDialog(null);
    } finally {
      setCommitting(false);
    }
  }

  function confirmDialog() {
    if (!dialog) return;
    if (dialog.type === "delete" && dialog.todo) {
      updateTodos(todos.filter((t) => t._uid !== dialog.todo._uid));
      setDialog(null);
      return;
    }
    if (dialog.type === "commit-one" && dialog.todo) {
      const fresh = todos.find((t) => t._uid === dialog.todo._uid) || dialog.todo;
      writeTodos([fresh]);
      return;
    }
    if (dialog.type === "commit-all") {
      writeTodos(todos);
    }
  }

  const dialogTitle =
    dialog?.type === "delete"
      ? "Remove this to-do?"
      : dialog?.type === "commit-one"
        ? "Write this to-do to Redmine?"
        : "Write all to-dos to Redmine?";

  const dialogCopy =
    dialog?.type === "delete"
      ? "It will leave your day plan. Hours are not auto-moved — edit another row if you want to reassign time."
      : dialog?.type === "commit-one"
        ? "Only this to-do and its hours will be written to Redmine. Other rows stay in your plan."
        : "All remaining to-dos in this plan will be written to Redmine with your edited hours.";

  return (
    <div className="page-block reveal">
      <header className="page-intro">
        <h1>Sync desk</h1>
        <p>
          Scan Git commits, weight the day, preview the plan — then write to-dos and hours to
          Redmine one row at a time, or all at once.
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
          {canCommitAll && (
            <button
              type="button"
              className="btn-accent"
              onClick={() => setDialog({ type: "commit-all" })}
              disabled={committing}
            >
              Write all to Redmine
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
                <h3>Plan for {result.date}</h3>
                <p>
                  Edit hours on a row, write that row to Redmine, or remove it. Use Write all when
                  the whole plan looks right.
                </p>
              </div>
              <button
                type="button"
                className="btn-accent"
                onClick={() => setDialog({ type: "commit-all" })}
                disabled={!canCommitAll}
              >
                Write all to Redmine
              </button>
            </div>
          )}

          {!result.dry_run && todos.length === 0 && (
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
                    ? "Change hours, then Write to Redmine on a row — or Remove it from the plan."
                    : result.date
                      ? `Plan for ${result.date}`
                      : "Bar width reflects relative hours in this plan."}
                </p>
              </div>
            </div>
            <ol>
              {todos.map((t, i) => (
                <li
                  key={t._uid}
                  className={`plan-row ${editable ? "is-editable" : ""}`}
                  style={{ "--i": i }}
                >
                  <div className="plan-index">{String(i + 1).padStart(2, "0")}</div>
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
                    </div>
                    <div className="plan-bar" aria-hidden="true">
                      <span style={{ width: `${Math.max(8, (t.hours / maxHours) * 100)}%` }} />
                    </div>
                    {editable && (
                      <div className="plan-row-actions">
                        <button
                          type="button"
                          className="btn-row-commit"
                          disabled={committing || !(Number(t.hours) > 0)}
                          onClick={() => setDialog({ type: "commit-one", todo: t })}
                          title="Write this to-do and hours to Redmine"
                          aria-label={`Write “${t.subject}” to Redmine`}
                        >
                          Write to Redmine
                        </button>
                        <button
                          type="button"
                          className="btn-row-remove"
                          disabled={committing}
                          onClick={() => setDialog({ type: "delete", todo: t })}
                        >
                          Remove
                        </button>
                      </div>
                    )}
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

      {dialog &&
        createPortal(
          <div
            className="modal-backdrop"
            role="presentation"
            onClick={() => !committing && setDialog(null)}
          >
            <div
              className="modal-card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="plan-dialog-title"
              onClick={(e) => e.stopPropagation()}
            >
              <p className={`modal-kicker ${dialog.type === "delete" ? "modal-kicker-danger" : ""}`}>
                {dialog.type === "delete" ? "Remove from plan" : "Write to Redmine"}
              </p>
              <h2 id="plan-dialog-title">{dialogTitle}</h2>
              <p className="modal-copy">{dialogCopy}</p>

              {dialog.todo && (
                <ul className="modal-preview">
                  <li>
                    <span>{dialog.todo.hours}h</span>
                    <p>{dialog.todo.subject}</p>
                  </li>
                </ul>
              )}

              {dialog.type === "commit-all" && (
                <>
                  <div className="modal-stats">
                    <div>
                      <span>Date</span>
                      <strong>{result?.date}</strong>
                    </div>
                    <div>
                      <span>To-dos</span>
                      <strong>{todos.length}</strong>
                    </div>
                    <div>
                      <span>Hours</span>
                      <strong>{result?.hours_logged}h</strong>
                    </div>
                  </div>
                  <ul className="modal-preview">
                    {todos.slice(0, 4).map((t) => (
                      <li key={t._uid}>
                        <span>{t.hours}h</span>
                        <p>{t.subject}</p>
                      </li>
                    ))}
                    {todos.length > 4 && <li className="more">+{todos.length - 4} more</li>}
                  </ul>
                </>
              )}

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setDialog(null)}
                  disabled={committing}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={dialog.type === "delete" ? "btn-danger" : "btn-accent"}
                  onClick={confirmDialog}
                  disabled={committing}
                >
                  {committing
                    ? "Writing to Redmine…"
                    : dialog.type === "delete"
                      ? "Yes, remove"
                      : dialog.type === "commit-one"
                        ? "Yes, write to Redmine"
                        : "Yes, write all to Redmine"}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
