import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useGoBack } from '@/lib/nav';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import { useRefreshDeals } from '@/lib/useBooking';
import type { Mentorship } from '@/api/types';
import { dayWord, time } from '@/lib/format';
import { DemoBadge, ErrorState, Footer, Hero, HeroTitle, LinkButton, Loading, Screen, Section, SlideToConfirm, Sticker, Strip, Switch, Ticket } from '@/ui';

export function MentorshipScreen() {
  const goBack = useGoBack();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['mentorship'], queryFn: api.mentorship });
  const put = (m: Mentorship) => qc.setQueryData(['mentorship'], m);
  const refresh = useRefreshDeals();
  const [acceptedName, setAcceptedName] = useState<string | null>(null);

  const toggle = useMutation({ mutationFn: (on: boolean) => api.setMentorAccepting(on), onSuccess: put });
  const accept = useMutation({ mutationFn: ({ id }: { id: string; name: string }) => api.acceptMentorRequest(id), onSuccess: (m, v) => {
      put(m);
      setAcceptedName(v.name);
      return refresh();
    },
  });
  const decline = useMutation({ mutationFn: (id: string) => api.declineMentorRequest(id), onSuccess: put });

  const back = { label: '‹ Назад', onClick: goBack };
  if (q.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={back} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const m = q.data;
  const on = toggle.isPending ? Boolean(toggle.variables) : m.accepting;
  const req = m.requests[0] ?? null;

  return (
    <Screen>
      <Hero
        nav={back}
        right={<DemoBadge />}
        caption="Наставничество"
        strip={<Strip items={[`Доступно после ${m.dealsRequired} дел`, `у тебя ${m.dealsDone}`]} />}
      >
        <HeroTitle
          text="Сходи с новичком на его первое дело"
          sticker={
            <Sticker style={{ fontSize: 14, lineHeight: '17px', padding: '11px 13px' }}>
              часы
              <br />
              как всем
            </Sticker>
          }
        />
      </Hero>

      <div className="body">
        {!m.eligible ? (
          <div className="text">
            Откроется после {m.dealsRequired} дел. Осталось {Math.max(0, m.dealsRequired - m.dealsDone)} — наставником становятся те, кто уже знает, как всё устроено.
          </div>
        ) : (
          <>
            <div className="list-row" style={{ borderBottom: 0, padding: 0 }}>
              <div className="stack stack--4">
                <span className="list-row__title" style={{ fontWeight: 700 }}>
                  Принимаю просьбы
                </span>
                <span className="meta">{on ? 'Новички по твоим интересам смогут позвать тебя с собой' : 'Сейчас ты не принимаешь просьбы'}</span>
              </div>
              <Switch label="Принимаю просьбы" checked={on} onChange={(v) => toggle.mutate(v)} />
            </div>
            {toggle.isError && <div className="error-text">{errorText(toggle.error, 'Не получилось переключить. Попробуй ещё раз.')}</div>}

            {on && (
              <Section title="Просят наставника">
                {req ? (
                  <Ticket
                    kicker={`${req.newbieName || 'Новичок'} · первое дело`}
                    title={req.deal.title}
                    lines={[dayWord(req.deal.startsAt)]}
                    time={time(req.deal.startsAt)}
                  />
                ) : acceptedName ? (
                  <div className="ok-text">Вы и {acceptedName} идёте вместе. Запись на ту же смену подтверждена.</div>
                ) : (
                  <div className="text" style={{ color: 'rgba(6,7,8,.72)' }}>
                    Сейчас просьб нет. Напишу, когда новичок пойдёт на дело по твоим интересам.
                  </div>
                )}
              </Section>
            )}

            <Section title="Мои новички" gap={4}>
              <div>
                {m.pairs.map((p) => (
                  <div key={p.id} className="list-row" style={{ alignItems: 'baseline' }}>
                    <div className="stack stack--4" style={{ minWidth: 0 }}>
                      <span className="list-row__title">{p.newbieName || 'Новичок'}</span>
                      <span className="meta">{p.dealTitle}</span>
                    </div>
                    <span className="list-row__value" style={{ fontSize: 16, lineHeight: '20px' }}>
                      {dayWord(p.startsAt)} {time(p.startsAt)}
                    </span>
                  </div>
                ))}
                {m.pairs.length === 0 && <div className="meta" style={{ padding: '12px 0' }}>Пока никого.</div>}
              </div>
            </Section>
          </>
        )}
      </div>

      <div className="spacer" />
      {m.eligible && on && req && (
        <Footer>
          <div className="meta center">Запишу тебя на ту же смену. Встретитесь у входа за 10 минут</div>
          <SlideToConfirm
            label="Сдвинь — пойду вместе"
            doneLabel="Идёте вместе"
            done={false}
            busy={accept.isPending}
            onConfirm={() => accept.mutate({ id: req.id, name: req.newbieName || 'новичок' })}
          />
          {(accept.isError || decline.isError) && (
            <div className="error-text center">{errorText(accept.error ?? decline.error, 'Не получилось ответить. Попробуй ещё раз.')}</div>
          )}
          <LinkButton disabled={decline.isPending} onClick={() => decline.mutate(req.id)}>
            Не смогу
          </LinkButton>
        </Footer>
      )}
    </Screen>
  );
}
