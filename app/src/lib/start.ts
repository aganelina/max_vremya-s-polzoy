import { getStartParam } from '@/max/bridge';

const START_ROUTES: Record<string, (token: string) => string> = {
  fr: (t) => `/i/${t}`,
  tr: (t) => `/t/${t}`,
  co: (t) => `/co/${t}`,
  org: (t) => `/org/${t}`,
  deal: (id) => `/deals/${id}`,
};

function urlStartParam(loc: Pick<Location, 'search' | 'hash'>): string | null {
  const q = new URLSearchParams(loc.search);
  const fromQuery = q.get('startapp') ?? q.get('WebAppStartParam');
  if (fromQuery) return fromQuery;
  const hash = loc.hash.replace(/^#\/?/, '');
  const i = hash.indexOf('?');
  return new URLSearchParams(i >= 0 ? hash.slice(i + 1) : hash).get('WebAppStartParam');
}

const initialLocation = { search: window.location.search, hash: window.location.hash };

export function startRoute(raw: string | null): string | null {
  if (!raw || !/^[A-Za-z0-9_-]{1,512}$/.test(raw)) return null;
  if (raw === 'my') return '/my';
  const i = raw.indexOf('_');
  if (i <= 0) return null;
  const route = START_ROUTES[raw.slice(0, i)] as ((t: string) => string) | undefined;
  const token = raw.slice(i + 1);
  return route && token ? route(token) : null;
}

export function readStartRoute(loc: Pick<Location, 'search' | 'hash'> = initialLocation): string | null {
  return startRoute(getStartParam() ?? urlStartParam(loc));
}
