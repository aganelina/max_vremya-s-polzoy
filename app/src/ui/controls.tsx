import { useId, type ReactNode } from 'react';

export interface ChipOption<T> {
  value: T;
  label: string;
  count?: number;
}

interface ChipsBase<T> {
  options: ChipOption<T>[];
  scroll?: boolean;
  label?: string;
}

export function Chips<T extends string | number>({
  options,
  value,
  onChange,
  scroll,
  label,
  allowNone,
}: ChipsBase<T> & { value: T | null; onChange: (v: T | null) => void; allowNone?: boolean }) {
  return (
    <div className={`chips${scroll ? ' chips--scroll' : ''}`} role="group" aria-label={label}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            className="chip"
            aria-pressed={on}
            onClick={() => onChange(on && allowNone ? null : o.value)}
          >
            <span>{o.label}</span>
            {o.count != null && <span className="chip__n">{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function MultiChips<T extends string>({
  options,
  value,
  onChange,
  label,
}: ChipsBase<T> & { value: T[]; onChange: (v: T[]) => void }) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <button
            key={o.value}
            type="button"
            className="chip"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== o.value) : [...value, o.value])}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function FieldGroup({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="stack">
      <div className="row row--between">
        <span className="caps">{label}</span>
        {hint && <span className="hint">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: ChipOption<T>[];
  value: T;
  onChange: (v: T) => void;
  label?: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Checkbox({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <button type="button" role="checkbox" aria-checked={checked} className="check" onClick={() => onChange(!checked)}>
      <span className="check__box" aria-hidden>
        {checked ? '✓' : ''}
      </span>
      {children}
    </button>
  );
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} className="switch" onClick={() => onChange(!checked)} />;
}

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  maxLength?: number;
  counter?: boolean;
  error?: string | false;
  multiline?: boolean;
  rows?: number;
  type?: string;
  hint?: string;
}

export function TextField({ label, value, onChange, placeholder, maxLength, counter, error, multiline, rows = 4, type = 'text', hint }: TextFieldProps) {
  const id = useId();
  const errId = `${id}-err`;
  const over = maxLength && value.length > maxLength * 0.875;
  const common = {
    id,
    value,
    placeholder,
    maxLength,
    className: `field${error ? ' field--error' : ''}`,
    'aria-invalid': Boolean(error),
    'aria-describedby': error ? errId : undefined,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(e.target.value),
  };
  return (
    <div className="stack">
      <div className="row row--between">
        <label className="caps" htmlFor={id}>
          {label}
        </label>
        {counter && maxLength ? (
          <span className="hint" style={over ? { color: 'var(--red)' } : undefined}>
            {value.length} / {maxLength}
          </span>
        ) : (
          hint && <span className="hint">{hint}</span>
        )}
      </div>
      {multiline ? <textarea rows={rows} {...common} /> : <input type={type} {...common} />}
      {error && (
        <div id={errId} className="error-text" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
