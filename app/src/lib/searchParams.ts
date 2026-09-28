import { useSearchParams } from 'react-router-dom';
import type { Origin, SearchParams, WhenSlot } from '@/api/types';

const DURATIONS = [30, 60, 120, 180] as const;
const WHENS: WhenSlot[] = ['now', 'tonight', 'tomorrow', 'weekend'];

export const DEFAULT_SEARCH: SearchParams = { durationMin: 120, when: 'tonight', from: 'campus' };
const LAST_KEY = 'vremya:last-search';

export function useSearchState() {
  const [sp, setSp] = useSearchParams();
  const d = Number(sp.get('d'));
  const w = sp.get('w') as WhenSlot;
  const f = sp.get('f') as Origin;
  const params: SearchParams = {
    durationMin: (DURATIONS as readonly number[]).includes(d) ? (d as SearchParams['durationMin']) : DEFAULT_SEARCH.durationMin,
    when: WHENS.includes(w) ? w : DEFAULT_SEARCH.when,
    from: f === 'home' || f === 'campus' ? f : DEFAULT_SEARCH.from,
    companyId: sp.get('co') ?? undefined,
    window: sp.get('wf') && sp.get('wt') ? { from: sp.get('wf')!, to: sp.get('wt')! } : undefined,
  };
  const set = (patch: Partial<SearchParams>) => {
    const next = { ...params, ...patch };
    const q = new URLSearchParams(sp);
    q.set('d', String(next.durationMin));
    q.set('w', next.when);
    q.set('f', next.from);
    if (next.companyId) q.set('co', next.companyId);
    else q.delete('co');
    if (patch.window) {
      q.set('wf', patch.window.from);
      q.set('wt', patch.window.to);
    } else {
      q.delete('wf');
      q.delete('wt');
    }
    setSp(q, { replace: true });
  };
  return { params, set, query: toQuery(params) };
}

export function toQuery(p: SearchParams) {
  const q = new URLSearchParams({ d: String(p.durationMin), w: p.when, f: p.from });
  if (p.companyId) q.set('co', p.companyId);
  if (p.window) {
    q.set('wf', p.window.from);
    q.set('wt', p.window.to);
  }
  return q.toString();
}

export function rememberSearch(p: SearchParams) {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify({ ...p, companyId: undefined, window: undefined }));
  } catch {
  }
}

export function lastSearch(): SearchParams | null {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    return raw ? (JSON.parse(raw) as SearchParams) : null;
  } catch {
    return null;
  }
}
