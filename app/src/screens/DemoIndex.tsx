import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, USE_MOCKS } from '@/api';
import { devUser, setDevUser } from '@/api/http';
import { errorText } from '@/lib/errors';
import { Chips, Hero, HeroTitle, Screen, Section } from '@/ui';
import { ymd } from '@/lib/format';

type Target = string | (() => Promise<string>);
type Item = [code: string, title: string, target: Target];

const tokenOf = (link: string, prefix: string) => new URL(link).searchParams.get('startapp')?.replace(`${prefix}_`, '') ?? '';

async function someDeal() {
  const my = await api.myDeals();
  if (my.upcoming[0]) return my.upcoming[0];
  const found = await api.search({ durationMin: 180, when: 'tomorrow', from: 'campus' });
  if (found.items[0]) return found.items[0].deal;
  throw new Error('Пока нет доступных дел. Попробуй позже.');
}
async function myBooking() {
  const d = (await api.myDeals()).upcoming.find((x) => x.myBooking?.status === 'going');
  if (!d?.myBooking) throw new Error('Нет активной записи — запишись на дело');
  return d.myBooking;
}
async function someShift() {
  const h = await api.coordHome();
  const s = h.next?.shift ?? h.shifts[0];
  if (!s) throw new Error('У организации нет смен');
  return s.id;
}
const friendToken = async () => tokenOf((await api.inviteLink((await someDeal()).id)).link, 'fr');

const live = !USE_MOCKS;
const pick = (mock: string, real: () => Promise<string>): Target => (live ? real : mock);

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: 'Участник',
    items: [
      ['3c', 'Главная: сколько у тебя времени', '/'],
      ['3e', 'Результаты поиска', '/search?d=120&w=tonight&f=campus'],
      ['3e', 'Поиск от дома: «в твоём районе»', '/search?d=180&w=tomorrow&f=home'],
      ['3e', 'В расписании нет окна: подсказка ближайшего', '/search?d=180&w=now&f=campus'],
      ['2d', 'Компания: общее окно', pick('/company/c-demo', async () => `/company/${(await api.createCompany(ymd())).id}`)],
      ['3a', 'Дело', pick('/deals/d-books', async () => `/deals/${(await someDeal()).id}`)],
      ['3b', 'Мои дела', '/my'],
      ['3d', 'Отметка на месте', pick('/deals/d-books/check-in', async () => `/deals/${(await someDeal()).id}/check-in`)],
      ['3f', 'Профиль', '/profile'],
      ['3g', 'Свободные окна', '/windows'],
      ['3h', 'Микро-дело не выходя из дома', '/micro'],
      ['3i', 'Банк часов', '/bank'],
      ['3j', 'Наставничество', '/mentor'],
      ['3s', 'Маршрут: два дела подряд', '/route'],
      ['3t', 'Передача места', pick('/t/ok', async () => `/t/${tokenOf((await api.transferLink((await myBooking()).id)).link, 'tr')}`)],
      ...(live ? [] : ([['3t', 'Передача места: забрали', '/t/taken']] as Item[])),
      ['3t', 'Передача места: устарела', pick('/t/expired', async () => '/t/demo-expired-token')],
      ['3q', 'Приглашение друга', pick('/i/ok', async () => `/i/${await friendToken()}`)],
      ...(live
        ? []
        : ([
            ['3q', 'Приглашение на заполненную смену', '/i/full'],
            ['3q', 'Истёкшее приглашение', '/i/expired'],
          ] as Item[])),
      ['3u', 'Справка о часах', '/certificate'],
      ['3v', 'Политика данных', '/privacy'],
      ['new', 'Заявка организации', '/orgs/apply'],
      ['org_', 'Приглашение координатора', '/org/demo-token'],
    ],
  },
  {
    title: 'Первый вход',
    items: [
      ['3q', 'Согласие', '/welcome'],
      ['3q', 'Согласие по ссылке друга', pick('/welcome?next=/i/ok', async () => `/welcome?next=${encodeURIComponent(`/i/${await friendToken()}`)}`)],
      ['3q', 'Согласие по передаче места', pick('/welcome?next=/t/ok', async () => `/welcome?next=${encodeURIComponent(`/t/${tokenOf((await api.transferLink((await myBooking()).id)).link, 'tr')}`)}`)],
      ['3r', 'Откуда считать дорогу', '/welcome/place'],
    ],
  },
  {
    title: 'Куратор',
    items: [
      ['3k', 'Кабинет', '/coord'],
      ['3l', 'Смена и явка', pick('/coord/shifts/s-books', async () => `/coord/shifts/${await someShift()}`)],
      ['3n', 'Новая смена', '/coord/shifts/new'],
      ['3o', 'Срочно', '/coord/urgent'],
      ['3p', 'Микро-дела на проверке', '/coord/reviews'],
      ['new', 'Микро-дела организации', '/coord/micro'],
      ['new', 'Новое микро-дело', '/coord/micro/new'],
      ['3w', 'Метрики', '/coord/metrics'],
      ['3x', 'Выгрузки и доступы', '/coord/access'],
      ['3y', 'Написать участникам', pick('/coord/shifts/s-books/message', async () => `/coord/shifts/${await someShift()}/message`)],
    ],
  },
  {
    title: 'Оператор',
    items: [
      ['new', 'Заявки организаций', '/operator/orgs'],
      ['3w', 'Метрики пилота: все организации', '/operator/metrics'],
    ],
  },
];

const DEV_USERS = [
  { value: '1', label: 'Алина · участник' },
  { value: '900206', label: 'Гульнара · координатор' },
  { value: '900205', label: 'Ринат · координатор' },
  { value: '777001', label: 'Новый пользователь' },
];

export function DemoIndex() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ key: string; text: string } | null>(null);
  const [user, setUser] = useState(devUser());
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, enabled: live });

  const go = async (key: string, t: Target) => {
    if (typeof t === 'string') return navigate(t);
    setBusy(key);
    setErr(null);
    try {
      navigate(await t());
    } catch (e) {
      setErr({ key, text: e instanceof Error && !('code' in e) ? e.message : errorText(e, 'Не получилось открыть экран') });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Screen>
      <Hero caption="Время с пользой">
        <HeroTitle text="Разделы" />
      </Hero>
      <div className="body">
        {live && import.meta.env.DEV && (
          <Section title="Кто я" aside={me.data ? `${me.data.firstName}${me.data.roles.coordinator ? ' · координатор' : ''}` : undefined} gap={8}>
            <Chips<string>
              label="Пользователь dev-стенда"
              options={DEV_USERS.some((u) => u.value === user) || !user ? DEV_USERS : [...DEV_USERS, { value: user, label: `MAX ${user}` }]}
              value={user}
              onChange={(v) => {
                if (!v) return;
                setDevUser(v);
                setUser(v);
                qc.clear();
              }}
            />
            <div className="meta">Заголовок X-Dev-User; бэкенд должен работать с APP_ENV=dev.</div>
          </Section>
        )}
        {GROUPS.map((g) => (
          <Section key={g.title} title={g.title} gap={4}>
            <div>
              {g.items.map(([, title, to]) => {
                const key = `${g.title}:${title}`;
                return (
                  <div key={key}>
                    <button type="button" className="list-row" disabled={busy === key} onClick={() => void go(key, to)}>
                      <span className="list-row__title">{busy === key ? 'Открываю…' : title}</span>
                      <span className="list-row__chev">›</span>
                    </button>
                    {err?.key === key && <div className="error-text">{err.text}</div>}
                  </div>
                );
              })}
            </div>
          </Section>
        ))}
      </div>
    </Screen>
  );
}
