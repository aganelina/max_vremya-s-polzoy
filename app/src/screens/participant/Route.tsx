import { Fragment, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useGoBack } from '@/lib/nav';
import { api, isApiError } from '@/api';
import { errorText } from '@/lib/errors';
import { useSearchState } from '@/lib/searchParams';
import { useRefreshDeals } from '@/lib/useBooking';
import type { Deal } from '@/api/types';
import { cap, dayWord, hoursStr, instructionLine, minutesBetween, time, clean } from '@/lib/format';
import { DemoBadge, ErrorState, Footer, Hero, HeroTimes, HeroTitle, LinkButton, Loading, Screen, SlideToConfirm, Sticker, Strip, Ticket } from '@/ui';

const dur = (d: Deal) => {
  const m = minutesBetween(d.startsAt, d.endsAt);
  return m < 60 ? `${m} мин` : `${hoursStr(m / 60)} ч`;
};

export function RouteScreen() {
  const navigate = useNavigate();
  const goBack = useGoBack();
  const refresh = useRefreshDeals();
  const [sp] = useSearchParams();
  const { params, query } = useSearchState();
  const p = sp.has('w') || sp.has('wf') ? params : undefined;
  const q = useQuery({
    queryKey: ['route', p ? query : null],
    queryFn: () => api.route(p),
    retry: (n, e) => !isApiError(e, 'no_route') && n < 1,
  });
  const [off, setOff] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const book = useMutation({
    mutationFn: (ids: string[]) => api.bookRoute(ids),
    onSuccess: () => {
      setDone(true);
      return refresh();
    },
  });

  const back = { label: '‹ Назад', onClick: goBack };
  if (q.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (isApiError(q.error, 'no_route'))
    return (
      <Screen>
        <Hero nav={back} right={<DemoBadge />} caption="Маршрут" strip={<Strip items={['Два дела подряд', 'до 15 минут пешком между ними']} />}>
          <HeroTitle text="В это окно два дела подряд не собрать" />
        </Hero>
        <div className="body">
          <div className="text">Не нашлось двух дел рядом друг с другом. Можно взять одно — подберу под твоё время.</div>
          <LinkButton start onClick={() => (p ? goBack() : navigate('/'))}>
            Найти одно дело
          </LinkButton>
        </div>
      </Screen>
    );
  if (q.isError) return <Screen><Hero nav={back} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const { window: win, legs } = q.data;
  const chosen = legs.filter((l) => !off.includes(l.deal.id)).map((l) => l.deal);
  const n = chosen.length;
  const first = chosen[0];
  const last = chosen[n - 1];
  const hours = chosen.reduce((s, d) => s + d.hours, 0);

  const toggle = (id: string) => {
    if (done) return;
    const isOn = !off.includes(id);
    if (isOn && n === 1) return;
    setOff((o) => (isOn ? [...o, id] : o.filter((x) => x !== id)));
  };

  const gapText = (i: number) => {
    const a = legs[i].deal;
    const b = legs[i + 1].deal;
    const aOn = !off.includes(a.id);
    const bOn = !off.includes(b.id);
    if (aOn && bOn) {
      const walk = legs[i].walkToNextMin ?? 0;
      return `≈${walk} мин пешком между адресами · запас ${minutesBetween(a.endsAt, b.startsAt) - walk} мин`;
    }
    if (aOn) return `после ${time(a.endsAt)} окно свободно`;
    return `окно свободно до ${time(b.startsAt)}`;
  };

  return (
    <Screen>
      <Hero
        nav={back}
        right={<DemoBadge />}
        caption={win ? `${cap(dayWord(win.from))} · окно ${hoursStr(minutesBetween(win.from, win.to) / 60)} ч · маршрут` : `${cap(dayWord(first.startsAt))} · маршрут`}
        strip={<Strip items={[`в зачёт ${hoursStr(hours)} ч`, `свободен в ${time(last.endsAt)}`]} />}
      >
        <HeroTimes
          from={time(first.startsAt)}
          to={time(last.endsAt)}
          sticker={
            <Sticker style={{ bottom: 'auto', top: 40, right: -4, fontSize: 15, padding: '12px 14px' }}>
              {n}
              <br />
              {n === 1 ? 'дело' : 'дела'}
            </Sticker>
          }
        />
      </Hero>

      <div style={{ display: 'flex', flexDirection: 'column', padding: '24px 24px 16px' }}>
        {legs.map((l, i) => {
          const on = !off.includes(l.deal.id);
          return (
            <Fragment key={l.deal.id}>
              <Ticket
                kicker={`${clean(l.deal.org.name)} · ${l.deal.address}`}
                title={l.deal.title}
                lines={[`${dur(l.deal)} · +${hoursStr(l.deal.hours)} ч`]}
                time={time(l.deal.startsAt)}
                stubLabel={on ? 'беру ✓' : 'не беру'}
                hotStub={on}
                off={!on}
                disabled={done || book.isPending}
                ariaLabel={`${l.deal.title}, ${on ? 'в маршруте' : 'убрано из маршрута'}`}
                onClick={() => toggle(l.deal.id)}
              />
              {i < legs.length - 1 && (
                <div style={{ display: 'grid', gridTemplateColumns: '24px minmax(0,1fr)', gap: 12, alignItems: 'center', padding: '8px 0 8px 16px', minHeight: 40 }}>
                  <span style={{ justifySelf: 'center', height: '100%', minHeight: 32, borderLeft: '2px dashed rgba(6,7,8,.4)' }} aria-hidden />
                  <span className="meta" style={{ color: 'rgba(6,7,8,.72)' }}>
                    {gapText(i)}
                  </span>
                </div>
              )}
            </Fragment>
          );
        })}
      </div>

      <div className="spacer" />
      <Footer>
        <SlideToConfirm
          label={n === 2 ? 'Сдвинь — беру оба дела' : 'Сдвинь — беру это дело'}
          doneLabel={n === 2 ? 'Записал на оба' : 'Записал'}
          done={done}
          busy={book.isPending}
          onConfirm={() => book.mutate(chosen.map((d) => d.id))}
        />
        {book.isError && <div className="error-text center">{errorText(book.error, 'Не получилось записать. Места могли занять — попробуй ещё раз.')}</div>}
        <div className="meta center" style={{ paddingTop: 4 }}>
          {done
            ? `${n === 2 ? 'Оба дела' : 'Дело'} в «Моих делах». ${instructionLine(first.instructionsAt, false)}`
            : 'Нажми на дело, чтобы убрать его из маршрута'}
        </div>
      </Footer>
    </Screen>
  );
}
