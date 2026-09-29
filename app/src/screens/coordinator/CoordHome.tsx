import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api';
import { cap, dayWord, time } from '@/lib/format';
import { ErrorState, Footer, Hero, HeroTimes, LinkButton, Loading, PrimaryButton, Screen, Sticker, Ticket } from '@/ui';
import { clean, CoordBadge } from './common';

type Filter = 'with' | 'all';

const TOOLS: [string, string][] = [
  ['Микро-дела', '/coord/micro'],
  ['Проверка', '/coord/reviews'],
  ['Метрики', '/coord/metrics'],
  ['Выгрузки', '/coord/access'],
];

export function CoordHomeScreen() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>('with');
  const q = useQuery({ queryKey: ['coord-home'], queryFn: api.coordHome });

  const nav = { label: '‹ Волонтёр', onClick: () => navigate('/') };
  if (q.isPending) return <Screen><Hero nav={nav} right={<CoordBadge />} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={nav} right={<CoordBadge />} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const { next, shifts } = q.data;
  const list = shifts.filter((s) => filter === 'all' || s.booked > 0);

  return (
    <Screen>
      <Hero
        nav={nav}
        right={<CoordBadge />}
        caption={next ? `${cap(dayWord(next.shift.startsAt))} · ближайшая смена` : 'Ближайших смен нет'}
        captionDot
        strip={
          next && (
            <button type="button" className="strip-btn" onClick={() => navigate(`/coord/shifts/${next.shift.id}`)}>
              <span className="strip-btn__title">{next.shift.title}</span>
              <span className="strip-btn__go">Открыть ›</span>
            </button>
          )
        }
      >
        {next ? (
          <HeroTimes
            from={time(next.shift.startsAt)}
            to={time(next.shift.endsAt)}
            sticker={
              <Sticker style={{ bottom: 'auto', top: 40, right: -4, fontSize: 15, padding: '12px 14px' }}>
                {next.going}
                <br />
                идут
              </Sticker>
            }
          />
        ) : (
          <div className="hero__main" />
        )}
      </Hero>

      <div className="body">
        <section className="stack stack--4">
          <div className="row" style={{ justifyContent: 'space-between', gap: 16, paddingBottom: 12 }}>
            <h2 className="h2">Смены</h2>
            <div className="mini-seg" role="group" aria-label="Какие смены показать">
              {(
                [
                  ['with', 'С записями'],
                  ['all', 'Все'],
                ] as [Filter, string][]
              ).map(([k, l]) => (
                <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div className="stack stack--12">
            {list.length === 0 && (
              <div className="card card--dashed">
                <div className="text">Пока никто не записался.</div>
                <LinkButton start onClick={() => setFilter('all')}>
                  Показать все смены
                </LinkButton>
              </div>
            )}
            {list.map((s) => (
              <Ticket
                key={s.id}
                title={s.title}
                lines={[`${dayWord(s.startsAt)} · ${clean(s.org.name)}`]}
                time={time(s.startsAt)}
                stubLabel={`${s.booked}/${s.capacity}`}
                hotStub={s.quorum && s.booked < s.capacity}
                onClick={() => navigate(`/coord/shifts/${s.id}`)}
                ariaLabel={`${s.title}, ${dayWord(s.startsAt)} в ${time(s.startsAt)}, записано ${s.booked} из ${s.capacity}${s.quorum ? ', собирается по кворуму' : ''}`}
              />
            ))}
          </div>
        </section>

        <section className="stack stack--4">
          <h2 className="h2" style={{ paddingBottom: 4 }}>
            Инструменты
          </h2>
          <div className="tools">
            {TOOLS.map(([l, to]) => (
              <LinkButton key={to} start style={{ padding: 0 }} onClick={() => navigate(to)}>
                {l}
              </LinkButton>
            ))}
          </div>
          <LinkButton start style={{ padding: 0 }} onClick={() => navigate('/coord/micro/new')}>
            + Новое микро-дело
          </LinkButton>
          <LinkButton start tone="danger" style={{ padding: 0 }} onClick={() => navigate('/coord/urgent')}>
            Нужна помощь срочно
          </LinkButton>
        </section>
      </div>

      <div className="spacer" />
      <Footer>
        <PrimaryButton onClick={() => navigate('/coord/shifts/new')}>Создать смену</PrimaryButton>
      </Footer>
    </Screen>
  );
}
