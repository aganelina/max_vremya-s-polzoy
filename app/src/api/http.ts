import { getInitData } from '@/max/bridge';
import type { Api } from './api';
import { ApiError } from './errors';
import type * as T from './types';

export { ApiError } from './errors';

const BASE = import.meta.env.VITE_API_BASE ?? '/api/v1';
const DEV_USER_KEY = 'vremya:dev-user';

export const apiUrl = (path: string) => new URL(BASE + path, window.location.href).href;

export function devUser(): string | null {
  if (!import.meta.env.DEV) return null;
  try {
    const picked = localStorage.getItem(DEV_USER_KEY);
    if (picked) return picked;
  } catch {
  }
  return import.meta.env.VITE_DEV_USER || null;
}

export function setDevUser(id: string | null) {
  try {
    if (id) localStorage.setItem(DEV_USER_KEY, id);
    else localStorage.removeItem(DEV_USER_KEY);
  } catch {
  }
}

type Query = Record<string, string | number | undefined>;

function authHeaders(): Record<string, string> {
  const init = getInitData();
  if (init) return { 'X-Max-Init-Data': init };
  const dev = devUser();
  return dev ? { 'X-Dev-User': dev } : {};
}

async function req<R>(method: string, path: string, opts: { body?: unknown; query?: Query; raw?: boolean; form?: FormData } = {}): Promise<R> {
  const params = opts.query ? Object.entries(opts.query).filter(([, v]) => v != null && v !== '') : [];
  const qs = params.length ? '?' + new URLSearchParams(params as [string, string][]).toString() : '';
  const headers = authHeaders();
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(BASE + path + qs, {
    method,
    headers,
    body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { code?: unknown };
    throw new ApiError(res.status, typeof err.code === 'string' ? err.code : 'http_error');
  }
  if (opts.raw) return (await res.blob()) as R;
  if (res.status === 204) return undefined as R;
  return res.json();
}

const get = <R>(p: string, query?: Query) => req<R>('GET', p, { query });
const post = <R>(p: string, body?: unknown) => req<R>('POST', p, { body: body ?? {} });
const put = <R>(p: string, body?: unknown) => req<R>('PUT', p, { body: body ?? {} });
const patch = <R>(p: string, body: unknown) => req<R>('PATCH', p, { body });
const del = <R>(p: string) => req<R>('DELETE', p);
const blob = (p: string, query?: Query) => req<Blob>('GET', p, { query, raw: true });
const search = (p: T.SearchParams): Query => ({ duration_min: p.durationMin, when: p.when, from: p.from, company_id: p.companyId, window_from: p.window?.from, window_to: p.window?.to });
const enc = encodeURIComponent;

function orgForm(p: T.OrgApplicationForm): FormData {
  const form = new FormData();
  for (const [k, v] of Object.entries(p)) {
    if (v == null || v === '') continue;
    form.append(k, v instanceof File ? v : String(v));
  }
  return form;
}

export const httpApi: Api = {
  me: () => get('/me'),
  dictionaries: () => get('/dictionaries'),
  consent: () => post('/me/consent'),
  onboard: (p) => post('/me/onboarding', p),
  updateProfile: (p) => patch('/me', p),
  exportData: () => post('/me/export'),
  deleteProfile: () => del('/me'),

  setWeeklySearch: (p) => put('/me/weekly-search', { params: p }),
  events: (date) => get('/events', { date }),
  searchPreview: (p) => get('/search/preview', search(p)),
  search: (p) => get('/search', search(p)),
  deal: (id, from) => get(`/deals/${enc(id)}`, { from }),
  book: (id, o) => post(`/deals/${enc(id)}/bookings`, o),
  cancelBooking: (id) => del(`/bookings/${enc(id)}`),
  inviteLink: (id) => post(`/deals/${enc(id)}/invite`),
  friendInvite: (t) => get(`/invites/${enc(t)}`),
  addToCalendar: async (id) => ({ icsUrl: apiUrl(`/deals/${enc(id)}/ics`) }),
  transferLink: (id) => post(`/bookings/${enc(id)}/transfer`),
  myDeals: () => get('/me/deals'),

  createCompany: (date) => post('/companies', { date }),
  joinCompany: (t) => post(`/companies/join/${enc(t)}`),
  company: (id) => get(`/companies/${enc(id)}`),
  setCompanyWindow: (id, window) => put(`/companies/${enc(id)}/window`, { window }),
  remind: (id, mid) => post(`/companies/${enc(id)}/members/${enc(mid)}/remind`),
  pickCompanyDeal: (id, dealId) => put(`/companies/${enc(id)}/pick`, { dealId }),

  checkIn: (id, code) => post(`/bookings/${enc(id)}/check-in`, { code }),
  undoCheckIn: (id) => del(`/bookings/${enc(id)}/check-in`),

  schedule: () => get('/me/schedule'),
  uploadSchedule: (file) => {
    const form = new FormData();
    form.append('file', file);
    return req('POST', '/me/schedule', { form });
  },

  nextMicroTask: (skipId) => get('/micro-tasks/next', { skip: skipId }),
  takeMicroTask: (id) => post(`/micro-tasks/${enc(id)}/take`),
  submitMicroTask: (id, answer) => post(`/micro-tasks/${enc(id)}/answer`, { answer }),
  releaseMicroTask: (id) => del(`/micro-tasks/${enc(id)}/take`),

  hourBank: () => get('/bank'),
  respondHelp: (id, on) => (on ? put(`/bank/requests/${enc(id)}/response`) : del(`/bank/requests/${enc(id)}/response`)),
  askHelp: (p) => post('/bank/requests', p),
  confirmHelp: (id) => post(`/bank/requests/${enc(id)}/received`),

  mentorship: () => get('/mentorship'),
  setMentorAccepting: (on) => patch('/mentorship', { accepting: on }),
  acceptMentorRequest: (id) => post(`/mentorship/requests/${enc(id)}/accept`),
  declineMentorRequest: (id) => post(`/mentorship/requests/${enc(id)}/decline`),

  route: (p) => get('/route', p && { duration_min: p.durationMin, when: p.when, from: p.from, window_from: p.window?.from, window_to: p.window?.to }),
  bookRoute: (dealIds) => post('/route/bookings', { dealIds }),

  seatTransfer: (t) => get(`/transfers/${enc(t)}`),
  claimSeat: (t) => post(`/transfers/${enc(t)}/claim`),

  certificate: (period) => get('/me/certificate', { period }),
  certificatePdf: (period) => blob('/me/certificate.pdf', { period }),
  certificateLink: (period) => req('POST', '/me/certificate/link', { query: { period }, body: {} }),
  shareCertificate: (period) => post('/me/certificate/share', { period }),

  coordHome: () => get('/coord/home'),
  attendance: (id) => get(`/coord/shifts/${enc(id)}/attendance`),
  markManual: (id, pid, on) =>
    on ? put(`/coord/shifts/${enc(id)}/participants/${enc(pid)}/manual`) : del(`/coord/shifts/${enc(id)}/participants/${enc(pid)}/manual`),
  checkInCode: (id) => get(`/coord/shifts/${enc(id)}/code`),
  cancelShift: (id) => post(`/coord/shifts/${enc(id)}/cancel`),
  createShift: (p) => post('/coord/shifts', p),
  urgentCall: (p) => post('/coord/urgent', p),
  urgentStatus: (id) => get(`/coord/urgent/${enc(id)}`),
  reviewQueue: () => get('/coord/reviews'),
  review: (id, verdict, note) => post(`/coord/reviews/${enc(id)}`, { verdict, note }),
  undoReview: (id) => del(`/coord/reviews/${enc(id)}`),
  metrics: () => get('/coord/metrics'),
  access: () => get('/coord/access'),
  exportAttendance: (p) => blob('/coord/attendance.csv', p),
  attendanceLink: (p) => req('POST', '/coord/attendance/link', { query: p, body: {} }),
  inviteCoordinator: () => post('/coord/access/invites'),
  setCoordinatorRevoked: (id, revoked) => patch(`/coord/access/${enc(id)}`, { revoked }),
  transferOwnership: (id) => post(`/coord/access/${enc(id)}/owner`),
  audiences: (id) => get(`/coord/shifts/${enc(id)}/audiences`),
  messageParticipants: (id, p) => post(`/coord/shifts/${enc(id)}/messages`, p),
  coordMicroTasks: () => get('/coord/micro-tasks'),
  createMicroTask: (p) => post('/coord/micro-tasks', p),
  setMicroTaskActive: (id, active) => patch(`/coord/micro-tasks/${enc(id)}`, { active }),

  applyOrg: (p) => req('POST', '/orgs', { form: orgForm(p) }),
  myOrgs: () => get('/orgs/mine'),

  operatorOrgs: (status) => get('/operator/orgs', { status }),
  operatorOrgImage: (id, kind) => blob(`/operator/orgs/${enc(id)}/${kind}.png`),
  verifyOrg: (id, p) => post(`/operator/orgs/${enc(id)}/verify`, p),
  rejectOrg: (id, reason) => post(`/operator/orgs/${enc(id)}/reject`, { reason }),
  operatorMetrics: () => get('/operator/metrics'),
};
