import { useId, useState } from "react";

function EyeIcon({ visible }) {
  /* Icon shows the action: open eye = reveal, slash = hide */
  if (visible) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M3 3l18 18M10.6 10.6a2.5 2.5 0 003.5 3.5M9.9 5.2A10.5 10.5 0 0112 5c5.5 0 9.5 4.5 10.5 7-.4 1-1.2 2.4-2.5 3.7M6.1 6.1C4.4 7.4 3.3 9 2.5 12c1 2.5 5 7 9.5 7 1.3 0 2.5-.3 3.6-.7"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M2.5 12C3.5 9.5 7.5 5 12 5s8.5 4.5 9.5 7c-1 2.5-5 7-9.5 7S3.5 14.5 2.5 12z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

/** Password / secret field with show-hide toggle. */
export default function SecretField({
  label,
  value,
  onChange,
  onFocus,
  placeholder,
  required,
  minLength,
  autoComplete = "off",
  badge,
  hint,
  name,
  /** "settings" reserves label/hint rows so grid columns align */
  layout = "default",
}) {
  const [visible, setVisible] = useState(false);
  const id = useId();
  const isSettings = layout === "settings";

  return (
    <label className={`field${isSettings ? " settings-field" : ""}`} htmlFor={id}>
      {(label || badge || isSettings) && (
        <span className="field-label-row">
          {label ? <span>{label}</span> : <span />}
          {badge || (isSettings ? <span className="field-badge-slot" aria-hidden="true" /> : null)}
        </span>
      )}
      <div className="secret-input-wrap">
        <input
          id={id}
          name={name}
          type={visible ? "text" : "password"}
          value={value ?? ""}
          placeholder={placeholder}
          required={required}
          minLength={minLength}
          autoComplete={autoComplete}
          spellCheck={false}
          onFocus={onFocus}
          onChange={onChange}
        />
        <button
          type="button"
          className="secret-toggle"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide value" : "Show value"}
          aria-pressed={visible}
          title={visible ? "Hide value" : "Show value"}
        >
          <EyeIcon visible={visible} />
        </button>
      </div>
      {isSettings ? (
        <span className={`field-hint${hint ? "" : " is-empty"}`}>{hint || "\u00a0"}</span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </label>
  );
}
