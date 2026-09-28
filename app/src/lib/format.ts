import type { Category, Origin, Transport, WhenSlot } from '@/api/types';

export const hoursStr = (h: number) => String(Math.round(h * 10) / 10).replace('.', ',');

export function plural(n: number, [one, few, many]: [string, string, string]) {
  const d = n % 10;
  const q = n % 100;
  if (d === 1 && q !== 11) return one;
  if (d >= 2 && d <= 4 && (q < 10 || q >= 20)) return few;
  return many;
}

export const DEALS: [string, string, string] = ['дело', 'дела', 'дел'];
export const PEOPLE: [string, string, string] = ['человек', 'человека', 'человек'];

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }).replace(/^0(\d):/, '$1:');

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

export function dayWord(iso: string, now = new Date()) {
  const diff = Math.round((startOfDay(new Date(iso)) - startOfDay(now)) / 86_400_000);
  if (diff === 0) return 'сегодня';
  if (diff === 1) return 'завтра';
  if (Math.abs(diff) >= 7) return new Date(iso).toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' });
  return new Date(iso).toLocaleDateString('ru-RU', { weekday: 'long' });
}

export function ymd(d: Date = new Date(), days = 0) {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
}

const STRIP_DEMO = import.meta.env.VITE_USE_MOCKS === 'true' || import.meta.env.DEV;
export const clean = (s: string) => (STRIP_DEMO ? s.replace(' (демо)', '') : s);

export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function weekdayDate(iso: string) {
  const d = new Date(iso);
  const wd = d.toLocaleDateString('ru-RU', { weekday: 'long' });
  const dm = d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
  return `${cap(wd)} ${dm}`;
}

export const dayMonth = (iso: string) => new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });

export const ddmm = (iso: string) => new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });

export function durationSticker(min: number): [string, string] {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (!h) return [String(m), 'мин'];
  return [m ? `${h} ч ${m}` : `${h} ч`, m ? 'мин' : 'окно'];
}

export const minutesBetween = (a: string, b: string) => Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60_000);

export const CATEGORY_LABEL: Record<Category, string> = {
  people: 'Люди',
  animals: 'Животные',
  ecology: 'Экология',
  books: 'Книги',
  things: 'Вещи',
  online: 'Онлайн',
};
export const CATEGORIES = Object.keys(CATEGORY_LABEL) as Category[];

export const TRANSPORT_LABEL: Record<Transport, string> = { walk: 'Пешком', transit: 'Транспорт', scooter: 'Самокат' };

export const WHEN_LABEL: Record<WhenSlot, string> = {
  now: 'Сейчас',
  tonight: 'Сегодня вечером',
  tomorrow: 'Завтра',
  weekend: 'В выходные',
};

export const DURATION_LABEL: Record<30 | 60 | 120 | 180, string> = { 30: '30 мин', 60: '1 ч', 120: '2 ч', 180: '3 ч и больше' };

export const travelLabel = (travelMin: number | null, from: Origin): string | null =>
  travelMin != null ? `≈${travelMin} мин` : from === 'home' ? 'в твоём районе' : null;

export const isNear = (travelMin: number | null, from: Origin) => (travelMin == null ? from === 'home' : travelMin <= 10);

export function instructionLine(instructionsAt: string, going: boolean, now = new Date()) {
  const later = new Date(instructionsAt).getTime() > now.getTime() + 60_000;
  if (going) return later ? 'Инструкцию пришлю вечером накануне' : 'Инструкция — в чате с ботом';
  return later ? 'Инструкцию пришлю вечером накануне' : 'Инструкцию пришлю сразу';
}

export function cancelLine(cancelUntil: string, now = new Date()) {
  if (new Date(cancelUntil).getTime() <= now.getTime()) return 'Отменить ещё можно, но отмена будет поздней';
  return `Отменить можно до ${time(cancelUntil)} ${dayWord(cancelUntil, now)}, без последствий`;
}
