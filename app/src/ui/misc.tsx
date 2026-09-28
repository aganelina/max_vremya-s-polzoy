import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { errorText } from '@/lib/errors';

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function PrimaryButton({ children, className, ...rest }: BtnProps) {
  return (
    <button type="button" className={['btn-primary', className].filter(Boolean).join(' ')} {...rest}>
      {children}
    </button>
  );
}

export function LinkButton({
  children,
  tone,
  start,
  className,
  ...rest
}: BtnProps & { tone?: 'danger' | 'ok'; start?: boolean }) {
  const cls = ['btn-link', tone && `btn-link--${tone}`, start && 'btn-link--start', className].filter(Boolean).join(' ');
  return (
    <button type="button" className={cls} {...rest}>
      {children}
    </button>
  );
}

export function PillButton({ children, tone, className, ...rest }: BtnProps & { tone?: 'ink' | 'danger' }) {
  const cls = ['btn-pill', tone && `btn-pill--${tone}`, className].filter(Boolean).join(' ');
  return (
    <button type="button" className={cls} {...rest}>
      {children}
    </button>
  );
}

export function Footer({ children }: { children: ReactNode }) {
  return <div className="footer">{children}</div>;
}

export function Screen({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <main className={`screen ${className}`}>{children}</main>;
}

export function Section({ title, aside, children, gap = 16 }: { title: string; aside?: ReactNode; children: ReactNode; gap?: 4 | 8 | 16 }) {
  return (
    <section className={`stack${gap === 16 ? ' stack--16' : gap === 4 ? ' stack--4' : ''}`}>
      <div className="row row--between">
        <h2 className="h2">{title}</h2>
        {aside && <span className="meta">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

interface TicketProps {
  title: string;
  kicker?: string;
  lines?: ReactNode[];
  note?: { text: string; tone?: 'ok' | 'warn' | 'bad' };
  time: string;
  stubLabel?: string;
  selected?: boolean;
  off?: boolean;
  hotStub?: boolean;
  onClick?: () => void;
  disabled?: boolean;
  ariaLabel?: string;
}

const NOTE_COLOR = { ok: 'var(--green)', warn: 'var(--red)', bad: 'var(--red)' } as const;

export function Ticket({ title, kicker, lines = [], note, time, stubLabel, selected, off, hotStub, onClick, disabled, ariaLabel }: TicketProps) {
  const cls = `ticket${selected ? ' ticket--on' : ''}${off ? ' ticket--off' : ''}`;
  const content = (
    <>
      <span className="ticket__body">
        {kicker && <span className="ticket__kicker">{kicker}</span>}
        <span className="ticket__title">{title}</span>
        {lines.map((l, i) => (
          <span key={i} className="ticket__line">
            {l}
          </span>
        ))}
        {note && (
          <span className="ticket__note" style={{ color: selected ? 'var(--orange)' : NOTE_COLOR[note.tone ?? 'ok'] }}>
            {note.text}
          </span>
        )}
      </span>
      <span className={`ticket__stub${hotStub ? ' ticket__stub--hot' : ''}`}>
        <span className="ticket__time">{time}</span>
        {stubLabel && <span className="ticket__stub-lbl">{stubLabel}</span>}
      </span>
    </>
  );
  if (!onClick) return <div className={cls}>{content}</div>;
  return (
    <button type="button" className={cls} onClick={onClick} disabled={disabled} aria-pressed={selected} aria-label={ariaLabel}>
      {content}
    </button>
  );
}

export function Avatar({ initial, grad, size, variant }: { initial?: string; grad?: 1 | 2 | 3; size?: 'sm'; variant?: 'empty' | 'pending' | 'seat' }) {
  const cls = ['avatar', size && `avatar--${size}`, grad && `grad-${grad}`, variant && `avatar--${variant}`].filter(Boolean).join(' ');
  return (
    <span className={cls} aria-hidden>
      {initial}
    </span>
  );
}

export function Toast({ text, action, onAction }: { text: string; action?: string; onAction?: () => void }) {
  return (
    <div className="toast" role="status">
      <span>{text}</span>
      {action && (
        <button type="button" className="btn-link" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}

export function Loading() {
  return (
    <div className="body" aria-busy="true" aria-label="Загрузка">
      <div className="skeleton" style={{ height: 24, width: '40%' }} />
      <div className="skeleton" style={{ height: 96 }} />
      <div className="skeleton" style={{ height: 96 }} />
    </div>
  );
}

const LOAD_FAILED = 'Не удалось загрузить. Проверь интернет и попробуй ещё раз.';

export function ErrorState({ onRetry, text, error }: { onRetry?: () => void; text?: string; error?: unknown }) {
  return (
    <div className="state">
      <div className="text">{text ?? errorText(error, LOAD_FAILED)}</div>
      {onRetry && <PillButton onClick={onRetry}>Повторить</PillButton>}
    </div>
  );
}
