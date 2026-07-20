import { useEffect, useState } from "react";
import { api } from "../api";
import { loadDayLogState, saveDayLogState } from "../dayLogState";

function todayLocal() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function TodosPage() {
  const initial = loadDayLogState();
  const [date, setDate] = useState(() => initial?.date || todayLocal());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(() => initial?.error ?? "");
  const [data, setData] = useState(() => initial?.data ?? null);

  useEffect(() => {
    saveDayLogState({ date, data, error });
  }, [date, data, error]);

  async function loadDay() {
    setBusy(true);
    setError("");
    try {
      const q = date ? `?date=${encodeURIComponent(date)}` : "";
      const res = await api(`/api/redmine/day${q}`);
      setData(res);
    } catch (err) {
      setData(null);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-block reveal">
      <header className="page-intro">
        <h1>Day log</h1>
        <p>
          See what already landed in Redmine for a day — time entries and linked issues — without
          leaving CommitFlow.
        </p>
      </header>

      <section className="control-strip">
        <label className="field compact">
          <span>Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <div className="control-actions">
          <button type="button" className="btn-primary" onClick={loadDay} disabled={busy || !date}>
            {busy ? "Loading…" : "Load day"}
          </button>
        </div>
      </section>

      {error && <p className="banner-error">{error}</p>}

      {data && (
        <section className="result-stage reveal">
          <div className="metric-row">
            <article>
              <p className="metric-label">Date</p>
              <p className="metric-value mode preview">{data.date}</p>
            </article>
            <article>
              <p className="metric-label">Entries</p>
              <p className="metric-value">{data.entry_count}</p>
            </article>
            <article>
              <p className="metric-label">Hours</p>
              <p className="metric-value">{data.total_hours}</p>
            </article>
            <article>
              <p className="metric-label">Source</p>
              <p className="metric-value mode preview">Redmine</p>
            </article>
          </div>

          <div className="plan-list day-log-list">
            <div className="plan-head">
              <div>
                <h2>Time logged</h2>
                <p>
                  Your Redmine time entries for {data.date}. Open an issue to inspect it on Redmine.
                </p>
              </div>
            </div>

            {data.entries?.length === 0 ? (
              <p className="plan-empty">No time entries for this day.</p>
            ) : (
              <ol>
                {data.entries.map((e, i) => (
                  <li key={e.id || `${e.issue_id}-${i}`} className="plan-row day-log-row" style={{ "--i": i }}>
                    <div className="plan-index">{String(i + 1).padStart(2, "0")}</div>
                    <div className="plan-body">
                      <div className="plan-topline">
                        <p className="plan-subject">
                          {e.issue_subject || (e.issue_id ? `Issue #${e.issue_id}` : "Time entry")}
                        </p>
                        <p className="plan-hours">{e.hours}h</p>
                      </div>
                      <div className="plan-meta">
                        {e.project_name && <span>{e.project_name}</span>}
                        {e.issue_id && <span className="chip">#{e.issue_id}</span>}
                        {e.issue_url && (
                          <a
                            className="day-log-link"
                            href={e.issue_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open in Redmine
                          </a>
                        )}
                      </div>
                      {e.comments ? <p className="day-log-comments">{e.comments}</p> : null}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
