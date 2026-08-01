const STORAGE_KEY = "cf_sync_desk_v1";

export function loadSyncDeskState() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return null;
    const hourGoal =
      data.hourGoal != null && Number.isFinite(Number(data.hourGoal))
        ? Number(data.hourGoal)
        : null;
    return {
      date: typeof data.date === "string" ? data.date : "",
      dryRun: data.dryRun !== false,
      result: data.result ?? null,
      error: typeof data.error === "string" ? data.error : "",
      hourGoal,
    };
  } catch {
    return null;
  }
}

export function saveSyncDeskState({ date, dryRun, result, error, hourGoal }) {
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        date: date || "",
        dryRun: dryRun !== false,
        result: result ?? null,
        error: error || "",
        hourGoal: hourGoal != null && Number.isFinite(Number(hourGoal)) ? Number(hourGoal) : null,
      })
    );
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearSyncDeskState() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
