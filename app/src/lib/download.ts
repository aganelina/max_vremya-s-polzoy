import type { FileLink } from '@/api/types';
import { canDownloadFile, downloadFile, openExternalLink } from '@/max/bridge';

export function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export class MaxDownloadError extends Error {
  constructor() {
    super('max_download_failed');
  }
}

export async function saveFile({
  name,
  fetchLink,
  fetchBlob,
}: {
  name: string;
  fetchLink: () => Promise<FileLink>;
  fetchBlob: () => Promise<Blob>;
}): Promise<'max' | 'browser'> {
  if (canDownloadFile()) {
    const link = await fetchLink();
    const url = new URL(link.url, window.location.href).href;
    if (await downloadFile(url, link.fileName || name)) return 'max';
    throw new MaxDownloadError();
  }
  downloadBlob(await fetchBlob(), name);
  return 'browser';
}

export async function savePublicFile(name: string, url: string): Promise<'max' | 'browser'> {
  if (canDownloadFile() && (await downloadFile(url, name))) return 'max';
  return openExternalLink(url) ? 'max' : 'browser';
}

export const SAVED_LABEL: Record<'max' | 'browser', string> = {
  max: 'Файл открыт в MAX',
  browser: 'Скачивание началось',
};
