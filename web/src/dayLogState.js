const STORAGE_KEY = "cf_day_log_v1";

export function loadDayLogState() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return null;
    return {
      date: typeof data.date === "string" ? data.date : "",
      data: data.data ?? null,
      error: typeof data.error === "string" ? data.error : "",
    };
  } catch {
    return null;
  }
}

export function saveDayLogState({ date, data, error }) {
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        date: date || "",
        data: data ?? null,
        error: error || "",
      })
    );
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearDayLogState() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
