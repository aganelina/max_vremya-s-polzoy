import type { Api } from './api';
import { devUser, httpApi } from './http';
import { getInitData } from '@/max/bridge';

export const MOCK_BUILD = import.meta.env.VITE_USE_MOCKS === 'true';
export const DEMO_AVAILABLE = MOCK_BUILD || import.meta.env.VITE_DEMO_ENABLED === 'true' || import.meta.env.VITE_DEMO_ENABLED === 'refresh';
export const DEMO_ACTIVE = DEMO_AVAILABLE && new URLSearchParams(window.location.search).get('demo') === '1';
export const USE_MOCKS = MOCK_BUILD || DEMO_ACTIVE;

export const hasApiSession = () => USE_MOCKS ? DEMO_ACTIVE : Boolean(getInitData() || devUser());

export function enterDemo() {
  if (!DEMO_AVAILABLE) return;
  const url = new URL(window.location.href);
  url.searchParams.set('demo', '1');
  if (!url.hash.startsWith('#/')) url.hash = '/';
  window.location.assign(url.href);
}

export function exitDemo() {
  window.location.assign(window.location.pathname);
}

export let api: Api = httpApi;

export async function initApi() {
  if (USE_MOCKS) api = (await import('./mock')).mockApi;
}

export type { Api } from './api';
export { ApiError, errorCode, isApiError } from './errors';
export * from './types';
