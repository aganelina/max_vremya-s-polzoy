import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useGoBack } from '@/lib/nav';
import { openMaxLink } from '@/max/bridge';
import { botChatLink } from '@/max/bot';
import { api } from '@/api';
import { cap, dayMonth, dayWord, hoursStr, plural, time } from '@/lib/format';
import { DemoBadge, ErrorState, Hero, HeroBig, LinkButton, Loading, Screen, Section, Sticker, Strip, Ticket } from '@/ui';

const WEEKS: [string, string, string] = ['неделя', 'недели', 'недель'];

function ScrollButton() {
  const [end, setEnd] = useState(false);
  useEffect(() => {
    const onScroll = () => setEnd(window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return (
    <div
      style={{
        position: 'sticky',
        bottom: 0,
        padding: '8px 24px calc(32px + var(--safe-bottom))',
        display: 'flex',
        justifyContent: 'center',
        pointerEvents: 'none',
      }}
    >
      <button
        type="button"
        aria-label={end ? 'Наверх' : 'Вниз'}
        onClick={() => window.scrollTo({ top: end ? 0 : document.documentElement.scrollHeight, behavior: 'smooth' })}
        style={{
          pointerEvents: 'auto',
          width: 56,
          height: 56,
          border: 0,
          borderRadius: 999,
          background: 'var(--orange)',
          color: 'var(--ink)',
          fontSize: 22,
          fontWeight: 800,
          boxShadow: '0 4px 12px rgba(6,7,8,.18)',
        }}
      >
        {end ? '↑' : '↓'}
      </button>
    </div>
  );
}

export function MyDealsScreen() {
  const navigate = useNavigate();
  const goBack = useGoBack();
  const me = useQuery({ queryKey: ['me'], queryFn: api.me });
  const q = useQuery({ queryKey: ['my-deals'], queryFn: api.myDeals });

  const s = me.data?.stats;
  const month = new Date().toLocaleDateString('ru-RU', { month: 'long' });
  const monthIn = month.endsWith('ь') || month.endsWith('й') ? month.slice(0, -1) + 'е' : month + 'е';
  const next = q.data?.upcoming[0];
  const statusLabel: Record<string, string> = { going: 'Ожидает отметки', checked_in: 'Участие отмечено', manual: 'Участие отмечено', done: 'Завершено', cancelled: 'Отменено', no_show: 'Неявка' };

  return (
    <Screen>
      <Hero
        nav={{ label: '‹ Назад', onClick: goBack }}
        right={<DemoBadge />}
        caption="Засчитано за учебный год"
        strip={s && <Strip items={[`${s.deals} ${plural(s.deals, ['доброе дело', 'добрых дела', 'добрых дел'])}`, `${hoursStr(s.hoursMonth)} ч в ${monthIn}`]} />}
      >
        <HeroBig
          value={s ? hoursStr(s.hoursYear) : '…'}
          unit="ч"
          sticker={
            s && s.streakWeeks > 1 ? (
              <Sticker top style={{ fontSize: 14, lineHeight: '17px', padding: '11px 13px' }}>
                {s.streakWeeks} {plural(s.streakWeeks, WEEKS)}
                <br />
                подряд
              </Sticker>
            ) : undefined
          }
        />
      </Hero>

      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <div className="body">
          <Section title="Ближайшее">
            {next ? (
              <Ticket
                selected
                kicker={cap(dayWord(next.startsAt))}
                title={next.title}
                lines={[next.address]}
                time={time(next.startsAt)}
                stubLabel="ИДЁШЬ"
                onClick={() => navigate(`/deals/${next.id}`)}
              />
            ) : (
              <div className="card card--dashed">
                <div className="text">Пока никуда не записан.</div>
                <LinkButton start onClick={() => navigate('/')}>
                  Найти дело под своё окно
                </LinkButton>
              </div>
            )}
            {q.data.upcoming.length > 1 && (
              <div className="stack stack--12">
                {q.data.upcoming.slice(1).map((d) => (
                  <Ticket
                    key={d.id}
                    kicker={cap(dayWord(d.startsAt))}
                    title={d.title}
                    lines={[d.address]}
                    time={time(d.startsAt)}
                    stubLabel="ИДЁШЬ"
                    onClick={() => navigate(`/deals/${d.id}`)}
                  />
                ))}
              </div>
            )}
          </Section>

          <Section title="Бот рядом" gap={8}>
            <div className="meta">Напоминания, инструкции и ответы координатора — в чате MAX. Там же доступны все записи и история.</div>
            <LinkButton start onClick={() => openMaxLink(botChatLink('my'))}>Открыть мои записи в боте</LinkButton>
            <LinkButton start onClick={() => openMaxLink(botChatLink('messages'))}>Выбрать событие и написать координатору</LinkButton>
          </Section>

          {q.data.past.length > 0 && <Section title="История записей" gap={16}>
            {q.data.past.map((b) => <div className="card" key={b.id}>
              <div className="meta">{dayMonth(b.startsAt)} · {time(b.startsAt)} · {statusLabel[b.status]}</div>
              <div className="ticket__title">{b.title}</div>
              <LinkButton start onClick={() => navigate(`/deals/${b.dealId}`)}>Открыть событие</LinkButton>
              {b.canContact && <LinkButton start onClick={() => openMaxLink(botChatLink(`contact_${b.id}`))}>Написать координатору</LinkButton>}
            </div>)}
          </Section>}
          <Section title="Засчитанные часы" gap={4}>
            {q.data.history.length === 0 ? (
              <div className="meta">Здесь появятся дела, за которые засчитаны часы.</div>
            ) : (
              <div>
                {q.data.history.map((h) => (
                  <div key={h.id} className="list-row" style={{ alignItems: 'baseline' }}>
                    <div className="stack stack--4" style={{ minWidth: 0 }}>
                      <span className="list-row__title">{h.title}</span>
                      <span className="meta">
                        {dayMonth(h.date)} · {h.place}
                      </span>
                    </div>
                    <span className="list-row__value">+{hoursStr(h.hours)}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>
      )}

      <div className="spacer" />
      {q.data && q.data.history.length > 4 && <ScrollButton />}
    </Screen>
  );
}
