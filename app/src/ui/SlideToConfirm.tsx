import { useEffect, useRef, useState } from 'react';
import { haptics } from '@/max/bridge';

interface SlideToConfirmProps {
  label: string;
  doneLabel: string;
  done: boolean;
  onConfirm: () => void;
  disabled?: boolean;
  disabledLabel?: string;
  onDisabledPress?: () => void;
  busy?: boolean;
}

const KNOB = 60;
const THRESHOLD = 0.8;

export function SlideToConfirm({ label, doneLabel, done, onConfirm, disabled, disabledLabel, onDisabledPress, busy }: SlideToConfirmProps) {
  const gesture = useRef({ start: 0, startY: 0, offset: 0, max: 0, moved: false, active: false });
  const suppressClick = useRef(false);
  const [x, setX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const off = Boolean(disabled || busy || done);
  const progress = done || busy ? 1 : x;
  useEffect(() => { if (!busy && !done) setX(0); }, [busy, done]);
  const text = disabled ? disabledLabel ?? label : busy ? 'Секунду…' : done ? doneLabel : label;

  const confirm = () => {
    if (off) return;
    haptics.impact('light');
    onConfirm();
  };
  const reset = () => {
    gesture.current.active = false;
    setDragging(false);
    setX(0);
  };

  return (
    <button
      type="button"
      className={`slide${dragging ? ' slide--dragging' : ''}${done ? ' slide--done' : ''}${disabled ? ' slide--off' : ''}`}
      aria-label={text}
      aria-disabled={off}
      aria-busy={Boolean(busy)}
      onClick={() => {
        if (suppressClick.current) {
          suppressClick.current = false;
          return;
        }
        if (disabled) onDisabledPress?.();
        else confirm();
      }}
      onPointerDown={(e) => {
        suppressClick.current = false;
        if (off || !e.isPrimary || e.button !== 0) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        gesture.current = { start: e.clientX, startY: e.clientY, offset: 0, max: Math.max(0, e.currentTarget.clientWidth - KNOB), moved: false, active: true };
        setDragging(true);
      }}
      onPointerMove={(e) => {
        const g = gesture.current;
        if (!g.active) return;
        const dx = e.clientX - g.start;
        if (Math.abs(dx) > 6 || Math.abs(e.clientY - g.startY) > 6) g.moved = true;
        g.offset = Math.max(0, Math.min(g.max, dx));
        setX(g.max ? g.offset / g.max : 0);
      }}
      onPointerUp={() => {
        const g = gesture.current;
        if (!g.active) return;
        suppressClick.current = g.moved;
        const complete = g.moved && g.max > 0 && g.offset >= g.max * THRESHOLD;
        gesture.current.active = false;
        setDragging(false);
        if (complete) { setX(1); confirm(); }
        else setX(0);
      }}
      onPointerCancel={() => { suppressClick.current = true; reset(); }}
      onLostPointerCapture={() => { if (gesture.current.active) reset(); }}
      onKeyDown={() => { suppressClick.current = false; }}
    >
      {!disabled && <span className="slide__fill" style={{ transform: `scaleX(${progress})` }} />}
      <span className="slide__label" style={{ opacity: done || disabled || busy ? 1 : Math.max(0, 1 - progress * 2) }} aria-live="polite">
        {text}
      </span>
      <span className="slide__travel" aria-hidden><span
        className="slide__knob"
        aria-hidden
        style={{ left: `${progress * 100}%` }}
      >
        {done ? '✓' : busy ? '…' : '→'}
      </span></span>
    </button>
  );
}
