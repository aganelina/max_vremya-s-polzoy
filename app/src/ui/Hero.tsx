import type { ReactNode } from 'react';

export type HeroTone = 'blue' | 'orange' | 'ink' | 'red' | 'paper';

interface HeroProps {
  tone?: HeroTone;
  striped?: boolean;
  nav?: { label: string; onClick: () => void };
  right?: ReactNode;
  caption?: ReactNode;
  captionDot?: boolean;
  children?: ReactNode;
  strip?: ReactNode;
}

export function Hero({ tone = 'blue', striped, nav, right, caption, captionDot, children, strip }: HeroProps) {
  return (
    <header className={`hero hero--${tone}${striped ? ' hero--striped' : ''}`}>
      <div className="hero__bar">
        {nav ? (
          <button type="button" className="hero__nav" onClick={nav.onClick}>
            {nav.label}
          </button>
        ) : (
          <span />
        )}
        {right}
      </div>
      {caption && (
        <div className="hero__caption">
          {captionDot && <span className="hero__dot" aria-hidden />}
          {caption}
        </div>
      )}
      {children}
      {strip}
    </header>
  );
}

export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}

export function DemoBadge({ role }: { role?: string }) {
  return role ? <Badge>{role}</Badge> : null;
}

export function HeroTitle({ children, text, sticker }: { children?: ReactNode; text: string; sticker?: ReactNode }) {
  const size = text.length <= 40 ? '' : text.length <= 70 ? ' hero__title--m' : ' hero__title--s';
  return (
    <div className="hero__main">
      <h1 className={`hero__title${size}${sticker ? ' hero__title--sticker' : ''}`} style={{ margin: 0 }}>
        {children ?? text}
      </h1>
      {sticker}
    </div>
  );
}

export function HeroBig({ value, unit, sticker }: { value: ReactNode; unit?: ReactNode; sticker?: ReactNode }) {
  return (
    <div className="hero__main">
      <div className="hero__big">
        <span>{value}</span>
        {unit && <span className="hero__big-unit">{unit}</span>}
      </div>
      {sticker}
    </div>
  );
}

export function HeroTimes({ from, to, sticker }: { from: string; to: string; sticker?: ReactNode }) {
  return (
    <div className="hero__main">
      <div className="hero__times" aria-label={`с ${from} до ${to}`}>
        <span>{from}</span>
        <span>{to}</span>
      </div>
      {sticker}
    </div>
  );
}

export function Sticker({
  children,
  white,
  top,
  style,
}: {
  children: ReactNode;
  white?: boolean;
  top?: boolean;
  style?: React.CSSProperties;
}) {
  return (
    <span className={`sticker${white ? ' sticker--white' : ''}${top ? ' sticker--top' : ''}`} style={style}>
      {children}
    </span>
  );
}

export function Strip({ items, children }: { items?: ReactNode[]; children?: ReactNode }) {
  return (
    <div className="strip">
      {items
        ? items.filter(Boolean).map((it, i) => (
            <span key={i} style={{ display: 'contents' }}>
              {i > 0 && (
                <span className="strip__sep" aria-hidden>
                  ✦
                </span>
              )}
              <span>{it}</span>
            </span>
          ))
        : children}
    </div>
  );
}

export function Ticker({ items }: { items: string[] }) {
  const line = items.map((t, i) => <span key={i}>{t} ✦</span>);
  return (
    <div className="ticker" aria-hidden>
      <div className="ticker__track">
        {line}
        {line}
        {line}
        {line}
      </div>
    </div>
  );
}
