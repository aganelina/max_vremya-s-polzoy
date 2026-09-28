export function botChatLink(payload?: string): string {
  const username = (import.meta.env.VITE_BOT_USERNAME || 'vremya_bot').replace(/^@/, '');
  const url = new URL(`https://max.ru/${encodeURIComponent(username)}`);
  if (payload) url.searchParams.set('start', payload);
  return url.href;
}

export function registrationPayload(route: string | null): string | undefined {
  if (route === '/my') return 'app_my';
  const match = route?.match(/^\/(deals|i|t|co|org)\/([A-Za-z0-9_-]+)(?:\?.*)?$/);
  if (!match) return undefined;
  const prefix: Record<string, string> = { deals: 'deal', i: 'fr', t: 'tr', co: 'co', org: 'org' };
  const payload = `app_${prefix[match[1]]}_${match[2]}`;
  return payload.length <= 512 ? payload : undefined;
}
