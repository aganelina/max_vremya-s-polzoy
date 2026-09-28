import type { ShareResult } from '@/max/bridge';

export const SHARED: Record<ShareResult, string> = {
  max: 'Отправлено в MAX ✓',
  system: 'Ссылка отправлена ✓',
  copied: 'Ссылка скопирована ✓',
  failed: 'Не получилось поделиться — скопируй ссылку вручную',
};
