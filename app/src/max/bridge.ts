export interface MaxUserUnsafe {
  id?: number | string;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
}

export interface MaxInitDataUnsafe {
  user?: MaxUserUnsafe;
  auth_date?: number;
  start_param?: string;
  query_id?: string;
  hash?: string;
}

interface BackButtonApi {
  show: () => void;
  hide: () => void;
  onClick: (cb: () => void) => void;
  offClick: (cb: () => void) => void;
}

interface HapticFeedbackApi {
  impactOccurred: (style?: string) => void;
  notificationOccurred: (type?: 'error' | 'success' | 'warning') => void;
  selectionChanged: () => void;
}

interface WebAppBridge {
  initData?: string;
  initDataUnsafe?: MaxInitDataUnsafe;
  platform?: string;
  version?: string;
  ready?: () => void;
  close?: () => void;
  openLink?: (url: string) => void;
  requestContact?: () => Promise<unknown>;
  shareMaxContent?: (params: { text?: string; link?: string }) => unknown;
  shareContent?: (params: { text?: string; link?: string }) => unknown;
  requestScreenMaxBrightness?: () => Promise<unknown>;
  restoreScreenBrightness?: () => Promise<unknown>;
  colorScheme?: 'light' | 'dark';
  BackButton?: BackButtonApi;
  HapticFeedback?: HapticFeedbackApi;
  openCodeReader?: (fileSelect?: boolean) => Promise<unknown> | unknown;
  downloadFile?: (url: string, fileName: string) => Promise<unknown> | unknown;
  openMaxLink?: (url: string) => void;
}

declare global {
  interface Window {
    WebApp?: WebAppBridge;
  }
}

const SCRIPT_LOAD_TIMEOUT_MS = 4000;

let loadPromise: Promise<boolean> | null = null;

export function loadMaxBridge(): Promise<boolean> {
  if (loadPromise) return loadPromise;

  if (typeof window !== 'undefined' && window.WebApp) {
    loadPromise = Promise.resolve(true);
    return loadPromise;
  }

  const src = import.meta.env.VITE_MAX_BRIDGE_URL;
  if (!src || typeof document === 'undefined') {
    loadPromise = Promise.resolve(false);
    return loadPromise;
  }

  loadPromise = new Promise<boolean>((resolve) => {
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };

    const timer = setTimeout(() => finish(false), SCRIPT_LOAD_TIMEOUT_MS);

    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = () => {
      clearTimeout(timer);
      finish(Boolean(window.WebApp));
    };
    script.onerror = () => {
      clearTimeout(timer);
      finish(false);
    };
    document.head.appendChild(script);
  });

  return loadPromise;
}

function getBridge(): WebAppBridge | undefined {
  return typeof window !== 'undefined' ? window.WebApp : undefined;
}

export function isBridgeAvailable(): boolean {
  return Boolean(getBridge()?.initData);
}

export function getInitData(): string | null {
  return getBridge()?.initData || null;
}

export function getInitDataUnsafe(): MaxInitDataUnsafe | null {
  return getBridge()?.initDataUnsafe ?? null;
}

export function getStartParam(): string | null {
  return getBridge()?.initDataUnsafe?.start_param ?? null;
}

export function getColorScheme(): 'light' | 'dark' | null {
  return getBridge()?.colorScheme ?? null;
}

export type MaxPlatform = 'ios' | 'android' | 'desktop' | 'web';

export function getMaxPlatform(): MaxPlatform | null {
  const raw = getBridge()?.platform?.toLowerCase();
  return raw === 'ios' || raw === 'android' || raw === 'desktop' || raw === 'web' ? raw : null;
}

export function getPlatform(): 'ios' | 'android' | null {
  const p = getMaxPlatform();
  if (!p) return null;
  return p === 'ios' ? 'ios' : 'android';
}

export function notifyReady(): void {
  getBridge()?.ready?.();
}

export function closeApp(): void {
  getBridge()?.close?.();
}

export function openExternalLink(url: string): boolean {
  const bridge = getBridge();
  if (bridge?.openLink) {
    bridge.openLink(url);
    return true;
  }
  if (typeof window !== 'undefined') window.open(url, '_blank', 'noopener,noreferrer');
  return false;
}

export function openMaxLink(url: string): void {
  const bridge = getBridge();
  if (bridge?.openMaxLink && new URL(url).searchParams.has('startapp')) bridge.openMaxLink(url);
  else openExternalLink(url);
}

export function hasCodeReader(): boolean {
  return Boolean(getBridge()?.initData && getBridge()?.openCodeReader);
}

export async function openCodeReader(fileSelect = true): Promise<string | null> {
  const fn = getBridge()?.openCodeReader;
  if (!fn) return null;
  try {
    const r = await fn(fileSelect);
    if (typeof r === 'string') return r;
    if (r && typeof r === 'object') {
      const o = r as Record<string, unknown>;
      const v = o.value ?? o.data ?? o.text ?? o.result;
      return typeof v === 'string' ? v : null;
    }
    return null;
  } catch {
    return null;
  }
}

export function canDownloadFile(): boolean {
  return Boolean(getBridge()?.initData && getBridge()?.downloadFile);
}

export async function downloadFile(url: string, fileName: string): Promise<boolean> {
  const fn = getBridge()?.downloadFile;
  if (!fn) return false;
  try {
    await fn(url, fileName);
    return true;
  } catch {
    return false;
  }
}

export type ShareResult = 'max' | 'system' | 'copied' | 'failed';

export async function shareLink(link: string, text: string): Promise<ShareResult> {
  const bridge = getBridge();
  try {
    if (bridge?.initData && bridge.shareMaxContent) {
      await bridge.shareMaxContent({ text, link });
      return 'max';
    }
    if (bridge?.initData && bridge.shareContent) {
      await bridge.shareContent({ text, link });
      return 'system';
    }
  } catch {
  }
  try {
    await navigator.clipboard.writeText(link);
    return 'copied';
  } catch {
    return 'failed';
  }
}

export const screenBrightness = {
  max(): void {
    void Promise.resolve(getBridge()?.requestScreenMaxBrightness?.()).catch(() => undefined);
  },
  restore(): void {
    void Promise.resolve(getBridge()?.restoreScreenBrightness?.()).catch(() => undefined);
  },
};

export const backButton = {
  show(): void {
    getBridge()?.BackButton?.show();
  },
  hide(): void {
    getBridge()?.BackButton?.hide();
  },
  onClick(cb: () => void): void {
    getBridge()?.BackButton?.onClick(cb);
  },
  offClick(cb: () => void): void {
    getBridge()?.BackButton?.offClick(cb);
  },
};

export const haptics = {
  impact(style?: string): void {
    getBridge()?.HapticFeedback?.impactOccurred(style);
  },
  notification(type?: 'error' | 'success' | 'warning'): void {
    getBridge()?.HapticFeedback?.notificationOccurred(type);
  },
  selection(): void {
    getBridge()?.HapticFeedback?.selectionChanged();
  },
};
