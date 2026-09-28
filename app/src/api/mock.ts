import type { Api } from './api';
import { ApiError } from './errors';
import type * as T from './types';
import { PILOT_DAYS, PILOT_WEEKS } from '@/lib/pilot';

const LATENCY = 250;
const wait = <R>(v: R): Promise<R> => new Promise((r) => setTimeout(() => r(structuredClone(v)), LATENCY));

function at(dayOffset: number, hm: string) {
  const [h, m] = hm.split(':').map(Number);
  const d = new Date();
  d.setDate(d.getDate() + dayOffset);
  d.setHours(h, m, 0, 0);
  return d.toISOString();
}
function weekday(dow: number, hm: string) {
  const today = ((new Date().getDay() + 6) % 7) + 1;
  return at((dow - today + 7) % 7, hm);
}
const addMin = (iso: string, min: number) => new Date(new Date(iso).getTime() + min * 60_000).toISOString();
const fail = (status: number, code: string): Promise<never> => new Promise((_, rej) => setTimeout(() => rej(new ApiError(status, code)), LATENCY));
function instructionsAt(startsAt: string) {
  const eve = new Date(startsAt);
  eve.setDate(eve.getDate() - 1);
  eve.setHours(19, 0, 0, 0);
  const now = new Date();
  return (eve < now ? now : eve).toISOString();
}

const ORG = {
  books: { id: 'o-books', name: 'Книжный мост', verified: true },
  aid: { id: 'o-aid', name: 'Пункт на Карла Маркса', verified: true },
  silver: { id: 'o-silver', name: 'Серебряный возраст', verified: true },
  food: { id: 'o-food', name: 'Фудбанк', verified: true },
  paw: { id: 'o-paw', name: 'Приют «Лапа»', verified: true },
  blood: { id: 'o-blood', name: 'Центр крови', verified: true },
  green: { id: 'o-green', name: 'Зелёная Казань', verified: true },
  home: { id: 'o-home', name: 'Фонд «Дом без стен»', verified: true },
} satisfies Record<string, T.Org>;

interface Seed {
  id: string;
  title: string;
  org: T.Org;
  category: T.Category;
  day: number;
  start: string;
  min: number;
  hours: number;
  address: string;
  addressNote?: string;
  travel: number;
  capacity: number;
  initials: string[];
  description: string;
  impact?: string;
}

const SEEDS: Seed[] = [
  {
    id: 'd-books', title: 'Разбор книг для сельских библиотек', org: ORG.books, category: 'books', day: 1, start: '18:00', min: 90, hours: 1.5,
    address: 'ул. Баумана, 19', addressNote: 'вход со двора', travel: 12, capacity: 8, initials: ['Д', 'М', 'К', 'Т', 'С'],
    description: 'Разобрать пожертвованные книги по возрасту и темам, упаковать в коробки для трёх сельских библиотек. Всё покажут на месте.',
    impact: '3 коробки книг уедут в сёла области',
  },
  {
    id: 'd-sort', title: 'Сортировка вещей в пункте помощи', org: ORG.aid, category: 'things', day: 0, start: '17:45', min: 60, hours: 1,
    address: 'ул. Карла Маркса, 40', travel: 7, capacity: 4, initials: ['Р'],
    description: 'Разложить принесённые вещи по размерам и сезонам, собрать наборы для семей. Перчатки выдадут.',
    impact: 'вещи дойдут до 20 семей на этой неделе',
  },
  {
    id: 'd-read', title: 'Чтение вслух в доме ветеранов', org: ORG.silver, category: 'people', day: 0, start: '18:10', min: 40, hours: 0.7,
    address: 'ул. Бутлерова, 31', travel: 9, capacity: 3, initials: ['Э'],
    description: 'Почитать вслух газету или рассказ, поговорить. Книги есть на месте.',
  },
  {
    id: 'd-food', title: 'Упаковка продуктовых наборов', org: ORG.food, category: 'things', day: 0, start: '18:30', min: 60, hours: 1,
    address: 'ул. Декабристов, 8', travel: 11, capacity: 10, initials: ['А', 'В', 'Г'],
    description: 'Собрать продуктовые наборы по списку и подписать коробки.',
  },
  {
    id: 'd-dogs', title: 'Выгул собак из приюта', org: ORG.paw, category: 'animals', day: 0, start: '18:20', min: 60, hours: 1,
    address: 'ул. Сибирский тракт, 34', travel: 15, capacity: 6, initials: ['Н', 'О'],
    description: 'Погулять с собаками в парке рядом с приютом. Поводки и пакеты выдадут.',
  },
  {
    id: 'd-blood', title: 'Помощь на донорской акции', org: ORG.blood, category: 'people', day: 0, start: '18:45', min: 30, hours: 0.5,
    address: 'ул. Пушкина, 3', travel: 10, capacity: 4, initials: [],
    description: 'Встречать доноров, помогать заполнить анкету, раздавать чай.',
  },
  {
    id: 'd-park', title: 'Уборка сквера у озера Кабан', org: ORG.green, category: 'ecology', day: 1, start: '17:00', min: 90, hours: 1.5,
    address: 'наб. озера Кабан', travel: 14, capacity: 5, initials: ['Л', 'Ф', 'Ш'],
    description: 'Собрать мусор вдоль набережной, рассортировать. Инвентарь выдадут.',
  },
];

const templates = [...SEEDS];
for (let day = 1; day <= PILOT_DAYS; day++) {
  ['09:30', '12:15', '16:00', '18:15'].forEach((start, slot) => {
    const template = templates[(day + slot) % templates.length];
    SEEDS.push({ ...template, id: `calendar-${day}-${slot}`, day, start, initials: template.initials.slice(0, 2) });
  });
}

const bookings = new Map<string, T.Booking>();

function toDeal(s: Seed, dayOverride?: number): T.Deal {
  const startsAt = at(dayOverride ?? s.day, s.start);
  const b = bookings.get(s.id) ?? null;
  const going = b && b.status !== 'cancelled';
  return {
    id: s.id,
    title: s.title,
    org: s.org,
    category: s.category,
    startsAt,
    endsAt: addMin(startsAt, s.min),
    hours: s.hours,
    address: s.address,
    addressNote: s.addressNote,
    description: s.description,
    travelMin: s.travel,
    capacity: s.capacity,
    taken: s.initials.length + (going ? 1 : 0),
    goingInitials: s.initials,
    checkInFrom: addMin(startsAt, -15),
    checkInTo: addMin(startsAt, 30),
    cancelUntil: addMin(startsAt, -180),
    instructionsAt: instructionsAt(startsAt),
    quorum: false,
    myBooking: going ? b : null,
    impact: s.impact,
  };
}
const seed = (id: string) => {
  const s = SEEDS.find((x) => x.id === id);
  if (!s) throw new Error('not_found');
  return s;
};


const me: T.Me = {
  id: 'u-alina',
  firstName: 'Алина',
  onboarded: true,
  consentAt: at(-30, '12:00'),
  university: { id: 'kfu', name: 'КФУ' },
  district: { id: 'vakh', name: 'Вахитовский' },
  interests: ['people', 'books'],
  transport: 'walk',
  notify: 'all',
  pauseUntil: null,
  weeklySearch: null,
  stats: { hoursYear: 4.5, hoursMonth: 2, deals: 3, streakWeeks: 3, bankBalance: 2.5 },
  roles: { coordinator: true, mentorEligible: true, operator: true },
};

const dictionaries: T.Dictionaries = {
  universities: ['КФУ', 'КНИТУ', 'КАИ', 'КГМУ', 'КГЭУ', 'КГАСУ', 'Другой'].map((name, i) => ({ id: i === 0 ? 'kfu' : `u${i}`, name })),
  districts: ['Вахитовский', 'Советский', 'Приволжский', 'Ново-Савиновский', 'Московский', 'Кировский', 'Авиастроительный'].map((name, i) => ({
    id: i === 0 ? 'vakh' : `d${i}`,
    name,
  })),
};

bookings.set('d-books', { id: 'b-books', dealId: 'd-books', status: 'going', checkedInAt: null });

const history: T.HistoryItem[] = [
  ['Высадка деревьев в парке Урицкого', -8, 'Зелёный патруль', 1.5],
  ['Письмо пожилому человеку', -15, 'микро-дело в чате', 0.5],
  ['Сортировка вещей в пункте помощи', -23, 'Пункт на Карла Маркса', 2.5],
  ['Чтение вслух в доме ветеранов', -32, 'Серебряный возраст', 1],
  ['Уборка берега озера Кабан', -43, 'Чистый город', 2],
  ['Выгул собак из приюта', -51, 'Приют «Лапа»', 1.5],
  ['Помощь на донорской акции', -65, 'Центр крови', 3],
  ['Расшифровка архивных писем', -73, 'микро-дело в чате', 0.5],
  ['Мастер-класс для детей в больнице', -86, 'Тёплые руки', 2],
].map(([title, d, place, hours], i) => ({ id: `h${i}`, title: title as string, date: at(d as number, '12:00'), place: place as string, hours: hours as number }));

const company = {
  id: 'c-demo',
  remindedAt: null as string | null,
  pickedDealId: 'd-books' as string | null,
  myWindow: { from: at(0, '17:00'), to: at(0, '19:40') } as { from: string; to: string } | null,
};

const MICRO: Omit<T.MicroTask, 'status' | 'deadline' | 'answer'>[] = [
  { id: 'm1', title: 'Проверь текст объявления о пристройстве собак', org: ORG.paw, minutes: 15, text: 'Прочитай объявление и предложи, как сделать его понятнее и теплее. Можно поправить заголовок или первые две строки.' },
  { id: 'm2', title: 'Подбери 5 книг для подростковой полки', org: ORG.books, minutes: 10, text: 'Напиши пять книг, которые ты бы сам посоветовал читателю 13–15 лет, и одну фразу, почему каждую.' },
  { id: 'm3', title: 'Напиши письмо пожилому человеку', org: ORG.silver, minutes: 20, text: 'Короткое тёплое письмо: пара слов о себе и вопрос, на который человеку будет приятно ответить. Координатор распечатает и передаст.' },
  {
    id: 'm4', title: 'Вопросы для интервью с выпускниками детского дома о первом годе самостоятельной жизни', org: ORG.home, minutes: 20,
    text: 'Предложи 5–7 вопросов: что было сложнее всего, кто помог, что бы они посоветовали тем, кто выпускается сейчас.',
  },
];
const microState = new Map<string, T.MicroTask>();
const micro = (i: number): T.MicroTask => microState.get(MICRO[i].id) ?? { ...MICRO[i], status: 'free', deadline: null, answer: '' };
let microIdx = 0;

const bank: Omit<T.HourBank, 'reserved'> = {
  balance: 2.5,
  maxOpenRequests: 3,
  others: [
    { id: 'o1', text: 'Подменить на стойке регистрации конференции', hours: 1, when: 'четверг, 12:00', district: 'Вахитовский район', mine: false, responded: false, helperName: null, status: 'open' },
    { id: 'o2', text: 'Помочь собрать шкаф в общежитии', hours: 2, when: 'суббота, 11:00', district: 'Вахитовский район', mine: false, responded: false, helperName: null, status: 'open' },
  ],
  mine: [{ id: 'my1', text: 'Помочь донести коробки на 4 этаж', hours: 1, when: 'среда, 18:00', district: 'Вахитовский район', mine: true, responded: false, helperName: 'Артур', status: 'matched' }],
};

const bankView = (): T.HourBank => ({
  ...bank,
  reserved: bank.mine.filter((m) => m.status !== 'closed').reduce((s, m) => s + m.hours, 0),
});

const mentor = { accepting: true, requestOpen: true, accepted: false };

const shiftSeeds: T.Shift[] = [
  ['s-books', 'Разбор книг для сельских библиотек', ORG.books, 'books', 1, '18:00', 90, 8, 6, false, 'ул. Пушкина, 12'],
  ['s-park', 'Уборка сквера у озера Кабан', ORG.green, 'ecology', 1, '17:00', 90, 5, 3, true, 'наб. озера Кабан'],
  ['s-flowers', 'Высадка цветов у корпуса', ORG.green, 'ecology', 1, '10:00', 120, 8, 4, false, 'ул. Кремлёвская, 18'],
  ['s-kids', 'Мастер-класс для детей', ORG.books, 'books', 2, '18:30', 90, 6, 0, false, 'ул. Пушкина, 12'],
  ['s-river', 'Уборка берега Казанки', ORG.green, 'ecology', 4, '11:00', 120, 12, 0, false, 'Кремлёвская набережная'],
].map(([id, title, org, category, day, start, min, capacity, booked, quorum, address]) => {
  const startsAt = at(day as number, start as string);
  return {
    id, title, org, category, startsAt, endsAt: addMin(startsAt, min as number), capacity, booked, quorum, address,
    instructions: 'Подойди к синему шатру у входа, спроси Гульнару', place: 'org', status: 'open',
  } as T.Shift;
});
const nextShift: T.Shift = {
  id: 's-food', title: 'Упаковка продуктовых наборов', org: ORG.food, category: 'things', startsAt: at(0, '19:30'), endsAt: at(0, '20:30'),
  address: 'ул. Декабристов, 8', capacity: 8, booked: 5, quorum: false, instructions: '', place: 'org', status: 'open',
};

const participants: T.Participant[] = [
  { id: 'p1', firstName: 'Алина', status: 'came', checkedInAt: at(1, '17:56') },
  { id: 'p2', firstName: 'Тимур', status: 'late', checkedInAt: at(1, '18:12') },
  { id: 'p3', firstName: 'Софья', status: 'booked', checkedInAt: null },
  { id: 'p4', firstName: 'Марат', status: 'booked', checkedInAt: null },
  { id: 'p5', firstName: 'Ильдар', status: 'no_show', checkedInAt: null },
];

const reviews: T.ReviewItem[] = [
  { id: 'a', authorName: 'Камила', minutes: 20, task: 'Вопросы для интервью с выпускниками детского дома', answer: '1. Что оказалось самым неожиданным в первый месяц? 2. Кто помог, когда было трудно? 3. Как ты искал жильё? 4. Что бы ты сказал себе в день выпуска? 5. Чему стоит учить в детском доме уже сейчас?' },
  { id: 'b', authorName: 'Руслан', minutes: 20, task: 'Напиши письмо пожилому человеку', answer: 'Здравствуйте! Меня зовут Руслан, я учусь на физфаке и люблю ходить пешком по старой Казани. А какая улица в городе была вашей любимой, когда вам было двадцать?' },
  { id: 'c', authorName: 'Алина', minutes: 15, task: 'Придумай подписи к фото из приюта', answer: 'Бублик: спит 20 часов в сутки, оставшиеся 4 ждёт тебя. Мира: осторожная, но если подружится — навсегда.' },
];
const reviewed = new Map<string, 'accept' | 'return'>();

const access: T.OrgAccess = {
  orgName: 'Книжный мост',
  shiftsThisMonth: 12,
  coordinators: [
    { id: 'c1', name: 'Гульнара', owner: true, me: true, revoked: false },
    { id: 'c2', name: 'Ринат', owner: false, me: false, revoked: false },
  ],
  invite: null,
};

let schedule: T.Schedule = {
  fileName: null,
  windows: [
    { id: 'w1', day: 'Вторник', from: '11:10', to: '13:10', startsAt: weekday(2, '11:10'), endsAt: weekday(2, '13:10'), after: 'после «История»', place: 'КФУ, главный' },
    { id: 'w2', day: 'Вторник', from: '14:40', to: '17:00', startsAt: weekday(2, '14:40'), endsAt: weekday(2, '17:00'), after: 'после «Обед с группой»', place: 'КФУ, главный' },
    { id: 'w3', day: 'Четверг', from: '15:10', to: '17:00', startsAt: weekday(4, '15:10'), endsAt: weekday(4, '17:00'), after: 'свободно до конца дня', place: 'КФУ, главный' },
  ],
};


const DUR_BASE = { 30: 3, 60: 7, 120: 12, 180: 15 } as const;
const WHEN_K = { now: 0.5, tonight: 1, tomorrow: 1.2, weekend: 1.4 } as const;
const WHEN_DAY = { now: 0, tonight: 0, tomorrow: 1, weekend: 4 } as const;
const SEARCH_ORDER = ['d-sort', 'd-books', 'd-read', 'd-food', 'd-dogs', 'd-blood'];

function noWindow(p: T.SearchParams): T.TimeWindow | null {
  if (p.window || p.companyId || p.when !== 'now' || p.durationMin < 120) return null;
  const today = at(0, '17:10');
  const from = new Date(today).getTime() > Date.now() + 30 * 60_000 ? today : at(1, '15:10');
  return { from, to: addMin(from, p.durationMin) };
}

function runSearch(p: T.SearchParams): T.SearchResult {
  const next = noWindow(p);
  if (next) return { window: null, windowSource: 'none', nextWindow: next, items: [], counts: { all: 0, near: 0 } };
  const day = WHEN_DAY[p.when];
  const company_ = Boolean(p.companyId);
  const dur = company_ ? 130 : p.durationMin;
  const from = p.window?.from ?? at(day, '17:30');
  const to = p.window?.to ?? addMin(from, dur);
  const share = ([0.3, 0.6, 1, 1][[30, 60, 120, 180].indexOf(p.durationMin)] ?? 1) * (p.when === 'now' ? 0.5 : 1);
  const ids = company_ ? SEARCH_ORDER : SEARCH_ORDER.slice(0, Math.max(1, Math.round(SEARCH_ORDER.length * share)));
  const slack: Record<string, number> = { 'd-sort': 25, 'd-books': 5, 'd-read': 40, 'd-food': 15, 'd-dogs': 10, 'd-blood': 30 };
  const items = ids.map((id) => {
    const d = toDeal(seed(id), day);
    if (id === 'd-books') {
      d.startsAt = at(day, '18:00');
      d.endsAt = addMin(d.startsAt, 90);
    }
    const travel = p.from === 'home' ? null : d.travelMin;
    return { deal: { ...d, travelMin: travel }, slackMin: slack[id], fit: slack[id] <= 5 ? 'tight' : 'ok' } as T.SearchResultItem;
  });
  const near = (d: T.Deal) => (d.travelMin == null ? d.org.id !== 'o-paw' && d.org.id !== 'o-food' : d.travelMin <= 10);
  const counts: T.SearchResult['counts'] = { all: items.length, near: items.filter((i) => near(i.deal)).length };
  for (const c of ['people', 'animals', 'ecology', 'books', 'things', 'online'] as T.Category[]) counts[c] = items.filter((i) => i.deal.category === c).length;
  const windowSource: T.WindowSource = p.window ? 'explicit' : company_ ? 'company' : 'schedule';
  return { window: { from, to }, windowSource, nextWindow: null, items, counts };
}

function companyView(): T.Company {
  const res = runSearch({ durationMin: 120, when: 'tonight', from: 'campus', companyId: company.id });
  return {
    id: company.id,
    date: at(0, '12:00'),
    commonWindow: { from: at(0, '17:30'), to: at(0, '19:40') },
    members: [
      { id: 'u-alina', firstName: 'Ты', initial: 'А', isMe: true, window: company.myWindow, remindedAt: null },
      { id: 'u-dima', firstName: 'Дима', initial: 'Д', isMe: false, window: { from: at(0, '17:30'), to: at(0, '21:00') }, remindedAt: null },
      { id: 'u-leila', firstName: 'Лейла', initial: 'Л', isMe: false, window: null, remindedAt: company.remindedAt },
    ],
    inviteLink: 'https://max.ru/vremya_bot?startapp=co_c-demo',
    deals: res.items.map((i) => ({ deal: i.deal, votes: i.deal.id === company.pickedDealId ? ['Ты', 'Дима'] : [] })),
    pickedDealId: company.pickedDealId,
  };
}


export const mockApi: Api = {
  events: (date) => wait(SEEDS.map((s) => toDeal(s)).filter((d) => {
    const at = new Date(d.startsAt);
    const local = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, '0')}-${String(at.getDate()).padStart(2, '0')}`;
    return local === date && new Date(d.endsAt).getTime() > Date.now();
  }).sort((a, b) => a.startsAt.localeCompare(b.startsAt))),
  me: () => wait(me),
  dictionaries: () => wait(dictionaries),
  consent: () => {
    me.consentAt = new Date().toISOString();
    return wait(me);
  },
  onboard: ({ universityId, districtId }) => {
    me.university = dictionaries.universities.find((u) => u.id === universityId) ?? null;
    me.district = dictionaries.districts.find((d) => d.id === districtId) ?? null;
    me.onboarded = true;
    return wait(me);
  },
  updateProfile: (p) => {
    if (p.interests) me.interests = p.interests;
    if (p.transport) me.transport = p.transport;
    if (p.notify) {
      me.notify = p.notify;
      me.pauseUntil = p.notify === 'pause' ? at(7, '00:00') : null;
    }
    if (p.universityId) me.university = dictionaries.universities.find((u) => u.id === p.universityId) ?? me.university;
    if (p.districtId) me.district = dictionaries.districts.find((d) => d.id === p.districtId) ?? me.district;
    return wait(me);
  },
  exportData: () => wait(undefined),
  deleteProfile: () => {
    me.onboarded = false;
    me.consentAt = null;
    return wait(undefined);
  },

  setWeeklySearch: (p) => {
    me.weeklySearch = p;
    return wait(undefined);
  },
  searchPreview: (p) =>
    wait<T.SearchPreview>(
      noWindow(p)
        ? { count: 0, windowSource: 'none' }
        : { count: Math.round(DUR_BASE[p.durationMin] * WHEN_K[p.when] * (p.from === 'home' ? 0.8 : 1)), windowSource: 'schedule' },
    ),
  search: (p) => wait(runSearch(p)),
  deal: (id, from) => {
    const s = SEEDS.find((x) => x.id === id);
    if (!s) return fail(404, 'deal_not_found');
    const d = toDeal(s);
    return wait(from === 'home' ? { ...d, travelMin: null } : d);
  },
  book: (dealId) => {
    const d = toDeal(seed(dealId));
    if (!d.myBooking && d.taken >= d.capacity) return fail(409, 'seat_taken');
    const b: T.Booking = { id: `b-${dealId}`, dealId, status: 'going', checkedInAt: null };
    bookings.set(dealId, b);
    return wait(b);
  },
  cancelBooking: (bookingId) => {
    for (const [k, b] of bookings) if (b.id === bookingId) bookings.delete(k);
    return wait(undefined);
  },
  inviteLink: () => wait({ link: 'https://max.ru/vremya_bot?startapp=fr_ok' }),
  friendInvite: (token) =>
    token === 'expired'
      ? wait<T.FriendInvite>({ status: 'expired', inviterName: 'Тимур', deal: toDeal(seed('d-read')) })
      : token === 'full'
        ? wait<T.FriendInvite>({ status: 'full', inviterName: 'Тимур', deal: { ...toDeal(seed('d-blood')), taken: 4 } })
        : wait<T.FriendInvite>({ status: 'ok', inviterName: 'Тимур', deal: toDeal(seed('d-books')) }),
  addToCalendar: (dealId) => wait({ icsUrl: new URL(`/api/v1/deals/${dealId}/ics`, window.location.href).href }),
  transferLink: () => wait({ link: 'https://max.ru/vremya_bot?startapp=tr_ok' }),
  myDeals: () => {
    const upcoming = [...bookings.values()].filter((b) => b.status === 'going' || b.status === 'checked_in').map((b) => toDeal(seed(b.dealId)));
    const past = [...bookings.values()].filter((b) => b.status === 'cancelled').map((b) => {
      const d = toDeal(seed(b.dealId));
      return { id: b.id, dealId: d.id, title: d.title, startsAt: d.startsAt, status: b.status, canContact: false };
    });
    return wait({ upcoming, history, past });
  },

  createCompany: () => wait(companyView()),
  joinCompany: () => wait(companyView()),
  company: () => wait(companyView()),
  setCompanyWindow: (_id, w) => {
    company.myWindow = w;
    return wait(companyView());
  },
  remind: () => {
    company.remindedAt = new Date().toISOString();
    return wait(undefined);
  },
  pickCompanyDeal: (_id, dealId) => {
    company.pickedDealId = dealId;
    return wait(companyView());
  },

  checkIn: (bookingId, code) => {
    if (code === '000000') return wait({ ok: false, error: 'expired' } as T.CheckInResult);
    const now = new Date().toISOString();
    for (const b of bookings.values()) if (b.id === bookingId) Object.assign(b, { status: 'checked_in', checkedInAt: now });
    return wait({ ok: true, checkedInAt: now, late: false });
  },
  undoCheckIn: (bookingId) => {
    for (const b of bookings.values()) if (b.id === bookingId) Object.assign(b, { status: 'going', checkedInAt: null });
    return wait(undefined);
  },

  schedule: () => wait(schedule),
  uploadSchedule: (file) => {
    schedule = { ...schedule, fileName: file.name };
    return wait(schedule);
  },

  nextMicroTask: (skipId) => {
    if (skipId) microIdx = (microIdx + 1) % MICRO.length;
    return wait(micro(microIdx));
  },
  takeMicroTask: (id) => {
    const t: T.MicroTask = { ...micro(MICRO.findIndex((m) => m.id === id)), status: 'taken', deadline: addMin(new Date().toISOString(), 120) };
    microState.set(id, t);
    return wait(t);
  },
  submitMicroTask: (id, answer) => {
    if (answer.trim().length < 10) return fail(422, 'answer_too_short');
    const t = { ...microState.get(id)!, status: 'sent' as const, answer };
    microState.set(id, t);
    return wait(t);
  },
  releaseMicroTask: (id) => {
    microState.delete(id);
    return wait(undefined);
  },

  hourBank: () => wait(bankView()),
  respondHelp: (id, on) => {
    const r = bank.others.find((o) => o.id === id);
    if (r) r.responded = on;
    return wait(bankView());
  },
  askHelp: ({ text, hours, when }) => {
    if (bank.mine.filter((m) => m.status !== 'closed').length >= bank.maxOpenRequests) return fail(409, 'too_many_requests');
    if (hours > bank.balance - bankView().reserved) return fail(409, 'insufficient_balance');
    bank.mine.unshift({ id: `my${Date.now()}`, text, hours, when: when || 'когда удобно', district: 'Вахитовский район', mine: true, responded: false, helperName: null, status: 'open' });
    return wait(bankView());
  },
  confirmHelp: (id) => {
    const r = bank.mine.find((m) => m.id === id);
    if (r && r.status !== 'closed') {
      r.status = 'closed';
      bank.balance = Math.max(0, bank.balance - r.hours);
    }
    return wait(bankView());
  },

  mentorship: () => wait(mentorView()),
  setMentorAccepting: (on) => {
    mentor.accepting = on;
    return wait(mentorView());
  },
  acceptMentorRequest: () => {
    mentor.accepted = true;
    mentor.requestOpen = false;
    return wait(mentorView());
  },
  declineMentorRequest: () => {
    mentor.requestOpen = false;
    return wait(mentorView());
  },

  route: (_p) =>
    wait({
      window: { from: at(0, '18:00'), to: at(0, '20:00') },
      legs: [
        { deal: toDeal(seed('d-read')), walkToNextMin: 7 },
        { deal: { ...toDeal(seed('d-sort')), startsAt: at(0, '19:00'), endsAt: at(0, '20:00') }, walkToNextMin: null },
      ],
    }),
  bookRoute: (ids) => {
    ids.forEach((id) => bookings.set(id, { id: `b-${id}`, dealId: id, status: 'going', checkedInAt: null }));
    return wait(undefined);
  },

  seatTransfer: (token) =>
    wait<T.SeatTransfer>(
      token === 'taken'
        ? { status: 'taken', fromName: 'Тимур', deal: null }
        : token === 'expired'
          ? { status: 'expired', fromName: null, deal: null }
          : { status: 'ok', fromName: 'Тимур', deal: toDeal(seed('d-books')) },
    ),
  claimSeat: () => {
    const b: T.Booking = { id: 'b-books', dealId: 'd-books', status: 'going', checkedInAt: null };
    bookings.set('d-books', b);
    return wait(b);
  },

  certificate: (period) => {
    const all = [
      { date: at(-8, '12:00'), title: 'Высадка деревьев в парке Урицкого', org: 'Зелёная Казань', hours: 1.5 },
      { date: at(-13, '12:00'), title: 'Письмо пожилому человеку', org: 'Серебряный возраст', hours: 0.5 },
      { date: at(-30, '12:00'), title: 'Разбор книг для сельских библиотек', org: 'Книжный мост', hours: 2.5 },
    ];
    const rows = period === 'semester' ? all.slice(0, 2) : all;
    return wait({
      period,
      periodLabel: period === 'semester' ? 'с 1 сентября' : 'всё время',
      generatedAt: new Date().toISOString(),
      participant: { firstName: me.firstName, university: me.university?.name ?? '' },
      rows,
      total: rows.reduce((s, r) => s + r.hours, 0),
      verifyCode: period === 'semester' ? 'K7Q-42M' : 'K7Q-91T',
      verifyUrl: 'vremya.ru/check',
    });
  },
  certificatePdf: () => wait(new Blob(['%PDF-1.4 demo'], { type: 'application/pdf' })),
  certificateLink: (period) =>
    wait({ url: new URL(`/api/v1/files/demo-spravka-${period}.pdf`, window.location.href).href, fileName: `spravka-${period}.pdf`, expiresAt: addMin(new Date().toISOString(), 5) }),
  shareCertificate: () => wait(undefined),

  coordHome: () => wait({ next: { shift: nextShift, going: 5 }, shifts: shiftSeeds.filter((s) => s.status === 'open') }),
  attendance: (id) => wait({ shift: shiftSeeds.find((s) => s.id === id) ?? shiftSeeds[0], participants }),
  markManual: (id, pid, on) => {
    const p = participants.find((x) => x.id === pid);
    if (p) Object.assign(p, on ? { status: 'manual', checkedInAt: new Date().toISOString() } : { status: 'booked', checkedInAt: null });
    return mockApi.attendance(id);
  },
  checkInCode: () => {
    const minute = Math.floor(Date.now() / 60_000);
    const code = String(482913 + (minute % 997) * 7).slice(-6);
    return wait({ code, qrPayload: `vremya:checkin:${code}`, expiresAt: new Date((minute + 1) * 60_000).toISOString() });
  },
  cancelShift: (id) => {
    const s = shiftSeeds.find((x) => x.id === id);
    if (s) s.status = 'cancelled';
    return wait(undefined);
  },
  createShift: (p) => {
    const startsAt = new Date(`${p.date}T${p.time}`).toISOString();
    const s: T.Shift = {
      id: `s-${Date.now()}`, title: p.title, org: ORG.books, category: p.category, startsAt, endsAt: addMin(startsAt, p.durationMin),
      address: 'ул. Пушкина, 12', capacity: p.capacity, booked: 0, quorum: p.quorum, instructions: p.instructions, place: p.place, status: 'open',
    };
    shiftSeeds.push(s);
    return wait(s);
  },
  urgentCall: (p) =>
    wait({
      id: `urg-${Date.now()}`, shiftId: 's-books', what: p.what, people: p.people, reached: Math.min(40, Math.max(15, p.people * 3)),
      responses: [{ name: 'Тимур', at: addMin(new Date().toISOString(), 2) }, { name: 'Алина', at: addMin(new Date().toISOString(), 5) }],
    }),
  urgentStatus: (id) => wait({ id, shiftId: 's-books', what: '', people: 3, reached: 15, responses: [] }),
  reviewQueue: () =>
    wait({
      items: reviews.filter((r) => !reviewed.has(r.id)),
      acceptedToday: [...reviewed.values()].filter((v) => v === 'accept').length,
      returnedToday: [...reviewed.values()].filter((v) => v === 'return').length,
    }),
  review: (id, verdict) => {
    reviewed.set(id, verdict);
    return wait(undefined);
  },
  undoReview: (id) => {
    reviewed.delete(id);
    return wait(undefined);
  },
  metrics: () => wait(metricsView(false)),
  operatorMetrics: () => wait(metricsView(true)),
  access: () => wait(access),
  exportAttendance: () => wait(new Blob(['date,shift,name,status,checked_in_at,hours\n'], { type: 'text/csv' })),
  attendanceLink: ({ from, to }) =>
    wait({ url: new URL('/api/v1/files/demo-yavka.csv', window.location.href).href, fileName: `yavka_${from}_${to}.csv`, expiresAt: addMin(new Date().toISOString(), 5) }),
  inviteCoordinator: () => {
    access.invite = { link: 'https://max.ru/vremya_bot?startapp=org_km7Qx2demo', expiresAt: at(7, '23:59') };
    return wait(access);
  },
  setCoordinatorRevoked: (id, revoked) => {
    const c = access.coordinators.find((x) => x.id === id);
    if (c) c.revoked = revoked;
    return wait(access);
  },
  transferOwnership: (id) => {
    const me = access.coordinators.find((x) => x.me);
    const c = access.coordinators.find((x) => x.id === id);
    if (!me?.owner) return fail(403, 'not_owner');
    if (c === me) return fail(409, 'cannot_transfer_to_self');
    if (!c || c.revoked) return fail(404, 'member_not_found');
    me.owner = false;
    c.owner = true;
    return wait(access);
  },
  audiences: () =>
    wait<T.Audience[]>([
      { key: 'all', names: participants.map((p) => p.firstName) },
      { key: 'waiting', names: participants.filter((p) => p.status === 'booked').map((p) => p.firstName) },
      { key: 'came', names: participants.filter((p) => ['came', 'late', 'manual'].includes(p.status)).map((p) => p.firstName) },
    ]),
  messageParticipants: async (id, p) => {
    const a = (await mockApi.audiences(id)).find((x) => x.key === p.audience);
    return { sent: a?.names.length ?? 0 };
  },

  coordMicroTasks: () => wait(coordMicro),
  createMicroTask: (p) => {
    if (p.minutes < 5 || p.minutes > 60) return fail(422, 'invalid_minutes');
    if (p.deadline && new Date(p.deadline) <= new Date()) return fail(422, 'deadline_in_past');
    const t: T.CoordMicroTask = { id: `cm${Date.now()}`, ...p, active: true, pending: 0, accepted: 0, createdAt: new Date().toISOString() };
    coordMicro.unshift(t);
    return wait(t);
  },
  setMicroTaskActive: (id, active) => {
    const t = coordMicro.find((x) => x.id === id);
    if (!t) return fail(404, 'micro_task_not_found');
    t.active = active;
    return wait(t);
  },

  applyOrg: (p) => {
    if (myOrgs.some((o) => o.status === 'pending')) return fail(409, 'application_pending');
    if (p.inn && !/^(\d{10}|\d{12})$/.test(p.inn)) return fail(422, 'invalid_inn');
    const o: T.OrgApplication = {
      id: `org${Date.now()}`, name: p.name, status: 'pending', rejectReason: null, role: 'owner', inn: p.inn ?? null, address: p.address,
      districtId: p.districtId ?? null, contactName: p.contactName, contactPhone: p.contactPhone, signName: p.signName ?? null,
      signPosition: p.signPosition ?? null, hasSeal: Boolean(p.seal), hasSignature: Boolean(p.signature), createdAt: new Date().toISOString(),
    };
    myOrgs.unshift(o);
    return wait(o);
  },
  myOrgs: () => wait(myOrgs),

  operatorOrgs: (status) => wait(operatorOrgs.filter((o) => !status || o.status === status)),
  operatorOrgImage: (_id, kind) =>
    wait(
      new Blob(
        [
          `<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><circle cx="60" cy="60" r="52" fill="none" stroke="#2250f4" stroke-width="6"/><text x="60" y="66" font-size="16" text-anchor="middle" fill="#2250f4">${kind === 'seal' ? 'ПЕЧАТЬ' : 'подпись'}</text></svg>`,
        ],
        { type: 'image/svg+xml' },
      ),
    ),
  verifyOrg: (id, { lat, lon, districtId }) => {
    const o = operatorOrgs.find((x) => x.id === id);
    if (!o) return fail(404, 'org_not_found');
    if (o.status !== 'pending') return fail(409, 'not_pending');
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return fail(422, 'invalid_point');
    if (districtId && !dictionaries.districts.some((d) => d.id === districtId)) return fail(422, 'unknown_district');
    Object.assign(o, { status: 'verified', verifiedAt: new Date().toISOString(), rejectReason: null, districtId: districtId ?? o.districtId });
    return wait(o);
  },
  rejectOrg: (id, reason) => {
    const o = operatorOrgs.find((x) => x.id === id);
    if (!o) return fail(404, 'org_not_found');
    if (o.status !== 'pending') return fail(409, 'not_pending');
    if (!reason.trim()) return fail(422, 'reason_required');
    Object.assign(o, { status: 'rejected', rejectReason: reason.trim() });
    return wait(o);
  },
};

const coordMicro: T.CoordMicroTask[] = [
  {
    id: 'cm1', title: 'Подбери 5 книг для подростковой полки', text: MICRO[1].text, minutes: 10, answersNeeded: 20, deadline: at(14, '23:59'),
    active: true, pending: 2, accepted: 7, createdAt: at(-6, '12:00'),
  },
  {
    id: 'cm2', title: 'Придумай подписи к фото с книжного обмена', text: 'Две-три строки к каждому фото: что за книга и кому она подойдёт.', minutes: 15,
    answersNeeded: 10, deadline: null, active: false, pending: 0, accepted: 10, createdAt: at(-20, '12:00'),
  },
];

const myOrgs: T.OrgApplication[] = [];

const orgCard = (id: string, name: string, extra: Partial<T.OperatorOrg>): T.OperatorOrg => ({
  id, name, status: 'pending', rejectReason: null, inn: null, address: '', districtId: 'vakh', contactName: '', contactPhone: '', signName: null,
  signPosition: null, hasSeal: false, hasSignature: false, createdByName: null, createdAt: at(-1, '12:00'), verifiedAt: null, ...extra,
});
const operatorOrgs: T.OperatorOrg[] = [
  orgCard('op1', 'Дом дружбы на Гоголя', {
    inn: '1655123456', address: 'ул. Гоголя, 11', contactName: 'Эльмира Хасанова', contactPhone: '+7 987 000-11-22', signName: 'Э. Р. Хасанова',
    signPosition: 'директор', hasSeal: true, hasSignature: true, createdByName: 'Эльмира', createdAt: at(-1, '10:20'),
  }),
  orgCard('op2', 'Клуб настольных игр «Ход»', {
    address: 'ул. Щапова, 26', districtId: 'd2', contactName: 'Артём', contactPhone: '+7 917 555-44-33', createdByName: 'Артём', createdAt: at(-3, '18:05'),
  }),
  orgCard('o-books', 'Книжный мост', {
    status: 'verified', inn: '1655000001', address: 'ул. Баумана, 19', contactName: 'Гульнара', contactPhone: '+7 900 000-00-01', createdByName: 'Гульнара',
    createdAt: at(-60, '12:00'), verifiedAt: at(-59, '12:00'),
  }),
];

function metricsView(all: boolean): T.Metrics {
  const orgs = all
    ? [
        { name: 'Книжный мост', attendance: 0.82, hours: 61 },
        { name: 'Зелёная Казань', attendance: 0.74, hours: 58.5 },
        { name: 'Серебряный возраст', attendance: 0.79, hours: 44 },
      ]
    : [
        { name: 'Книжный мост', attendance: 0.82, hours: 61 },
        { name: 'В среднем по пилоту', attendance: 0.78, hours: 54.5 },
      ];
  return {
    periodLabel: `Пилот · за ${PILOT_WEEKS} недель`,
    hours: 163.5,
    participants: 87,
    returnedShare: 0.41,
    funnel: [
      { label: 'Указали окно', value: 412, note: 'все, кто открыл подбор' },
      { label: 'Записались', value: 138, note: '33% от окон' },
      { label: 'Пришли', value: 104, note: '75% от записей' },
    ],
    orgs,
  };
}

function mentorView(): T.Mentorship {
  return {
    eligible: true,
    dealsDone: 3,
    dealsRequired: 3,
    accepting: mentor.accepting,
    requests: mentor.accepting && mentor.requestOpen ? [{ id: 'mr1', newbieName: 'Камила', deal: toDeal(seed('d-park')) }] : [],
    pairs: [
      ...(mentor.accepted ? [{ id: 'pk', newbieName: 'Камила', dealTitle: 'Уборка сквера у озера Кабан', startsAt: at(1, '17:00') }] : []),
      { id: 'pr', newbieName: 'Руслан', dealTitle: 'Высадка цветов у корпуса', startsAt: at(1, '10:00') },
    ],
  };
}
