import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useGoBack } from '@/lib/nav';
import { api, isApiError } from '@/api';
import type { Booking, Category, Origin, SearchParams, WhenSlot } from '@/api/types';
import { CATEGORIES, CATEGORY_LABEL, DEALS, DURATION_LABEL, WHEN_LABEL, cancelLine, cap, dayWord, durationSticker, hoursStr, instructionLine, isNear, minutesBetween, plural, time, travelLabel, ymd, clean } from '@/lib/format';
import { errorText } from '@/lib/errors';
import { useSearchState } from '@/lib/searchParams';
import { useBooking } from '@/lib/useBooking';
import { Chips, DemoBadge, ErrorState, FieldGroup, Footer, Hero, HeroTimes, LinkButton, Loading, PrimaryButton, Screen, SlideToConfirm, Sticker, Ticket } from '@/ui';

type Filter = 'all' | 'near' | Category;
const FIRST = 3;

const need = (min: number) => (min < 60 ? `${min} мин` : `${hoursStr(min / 60)} ч`);

export function SearchScreen() {
  const navigate = useNavigate();
  const goBack = useGoBack();
  const { params, set, query } = useSearchState();
  const [edit, setEdit] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState<string | null>(null);
  const [booked, setBooked] = useState<Booking | null>(null);
  const { book, cancel } = useBooking();

  const q = useQuery({ queryKey: ['search', params], queryFn: () => api.search(params), placeholderData: (p) => p });
  const company = useMutation({
    mutationFn: () => api.createCompany(ymd(q.data?.window ? new Date(q.data.window.from) : new Date())),
    onSuccess: (c) => navigate(`/company/${c.id}`),
  });

  const items = (q.data?.items ?? []).filter((i) =>
    filter === 'all' ? true : filter === 'near' ? isNear(i.deal.travelMin, params.from) : i.deal.category === filter,
  );
  const shown = open ? items : items.slice(0, FIRST);
  const rest = items.length - shown.length;
  const picked = q.data?.items.find((i) => i.deal.id === pick)?.deal ?? null;

  const win = q.data?.window ?? null;
  const noWindow = q.data?.windowSource === 'none';
  const next = noWindow ? q.data!.nextWindow : null;
  const [durA, durB] = durationSticker(win ? minutesBetween(win.from, win.to) : params.durationMin);
  const total = q.data?.items.length ?? 0;
  const whenLabel = params.window ? cap(dayWord(params.window.from)) : WHEN_LABEL[params.when];
  const paramsLine = [params.window ? need(minutesBetween(params.window.from, params.window.to)) : DURATION_LABEL[params.durationMin], whenLabel.toLowerCase(), params.from === 'home' ? 'от дома' : 'от вуза'].join(' · ');

  const changeParams = (p: Partial<SearchParams>) => {
    set(p);
    setPick(null);
    setBooked(null);
  };

  const filters: { value: Filter; label: string; count: number }[] = [
    { value: 'all', label: 'Все', count: q.data?.counts.all ?? 0 },
    { value: 'near', label: 'До 10 мин', count: q.data?.counts.near ?? 0 },
    ...CATEGORIES.filter((c) => (q.data?.counts[c] ?? 0) > 0).map((c) => ({ value: c as Filter, label: CATEGORY_LABEL[c], count: q.data?.counts[c] ?? 0 })),
  ];

  return (
    <Screen>
      <Hero
        tone={noWindow ? 'ink' : 'blue'}
        striped={noWindow}
        nav={{ label: '‹ Назад', onClick: goBack }}
        right={<DemoBadge />}
        caption={noWindow ? `${whenLabel} · в расписании занято` : `${whenLabel} · твоё окно`}
        captionDot={!noWindow}
        strip={
          <div className="strip" style={{ justifyContent: 'space-between', flexWrap: 'nowrap', padding: '4px 16px 4px 24px', minHeight: 52 }}>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span className="strip__num">
                {total} {plural(total, DEALS)}
              </span>{' '}
              · {paramsLine}
            </span>
            <button
              type="button"
              className="btn-pill"
              aria-expanded={edit}
              style={{ borderColor: 'var(--orange)', color: 'var(--orange)' }}
              onClick={() => setEdit((e) => !e)}
            >
              {edit ? 'Готово' : 'Изменить'}
            </button>
          </div>
        }
      >
        {noWindow ? (
          <HeroTimes
            from="—"
            to="—"
            sticker={
              <Sticker style={{ bottom: 'auto', top: 40, right: -4, fontSize: 15, padding: '12px 14px', transform: 'rotate(-6deg)' }}>
                окна
                <br />
                нет
              </Sticker>
            }
          />
        ) : (
          <HeroTimes
            from={win ? time(win.from) : '…'}
            to={win ? time(win.to) : '…'}
            sticker={
              <Sticker style={{ bottom: 'auto', top: 40, right: -4, fontSize: 15, padding: '12px 14px' }}>
                {durA}
                <br />
                {durB}
              </Sticker>
            }
          />
        )}
      </Hero>

      {edit && (
        <div className="stack stack--16" style={{ padding: '24px 24px 8px', borderBottom: '2px solid var(--ink)' }}>
          <FieldGroup label="Сколько времени">
            <Chips<SearchParams['durationMin']>
              options={([30, 60, 120, 180] as const).map((v) => ({ value: v, label: DURATION_LABEL[v] }))}
              value={params.durationMin}
              onChange={(v) => v && changeParams({ durationMin: v })}
            />
          </FieldGroup>
          <FieldGroup label="Когда">
            <Chips<WhenSlot>
              options={(Object.keys(WHEN_LABEL) as WhenSlot[]).map((v) => ({ value: v, label: WHEN_LABEL[v] }))}
              value={params.when}
              onChange={(v) => v && changeParams({ when: v })}
            />
          </FieldGroup>
          <FieldGroup label="Откуда идёшь">
            <Chips<Origin>
              options={[
                { value: 'campus', label: 'От вуза' },
                { value: 'home', label: 'От дома' },
              ]}
              value={params.from}
              onChange={(v) => v && changeParams({ from: v })}
            />
          </FieldGroup>
        </div>
      )}

      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} text={isApiError(q.error, 'bad_window') ? 'Это окно уже прошло. Выбери другое время.' : undefined} />
      ) : noWindow ? (
        <div className="stack stack--16" style={{ padding: '24px 24px 0' }}>
          <div className="card card--dashed" style={{ gap: 12 }}>
            <h2 className="h2" style={{ margin: 0, textWrap: 'pretty' }}>
              В расписании нет свободных {need(params.durationMin)} {WHEN_LABEL[params.when].toLowerCase()}
            </h2>
            <div className="text">
              {next
                ? `Ближайшее свободное окно — ${dayWord(next.from)} ${time(next.from)}–${time(next.to)}. Подберу дела под него.`
                : 'Ближайших свободных окон такой длины нет. Попробуй меньше времени или другой день.'}
            </div>
            {next && (
              <PrimaryButton onClick={() => changeParams({ window: next })}>
                Найти на {dayWord(next.from)} {time(next.from)}–{time(next.to)}
              </PrimaryButton>
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <LinkButton onClick={() => setEdit(true)}>Изменить время</LinkButton>
            <LinkButton onClick={() => navigate('/windows')}>Мои свободные окна</LinkButton>
          </div>
        </div>
      ) : (
        <>
          <div style={{ padding: '24px 24px 16px' }}>
            <Chips<Filter>
              scroll
              label="Фильтр"
              options={filters}
              value={filter}
              onChange={(v) => {
                setFilter(v ?? 'all');
                setOpen(false);
              }}
            />
          </div>
          <div className="stack stack--12" style={{ padding: '0 24px' }}>
            {shown.length === 0 && (
              <div className="card card--dashed">
                <div className="text">В это окно по фильтру ничего нет.</div>
                <LinkButton start onClick={() => setFilter('all')}>
                  Показать все дела
                </LinkButton>
              </div>
            )}
            {shown.map(({ deal, slackMin, fit }) => (
              <Ticket
                key={deal.id}
                title={deal.title}
                lines={[[clean(deal.org.name), travelLabel(deal.travelMin, params.from)].filter(Boolean).join(' · ')]}
                note={{ text: fit === 'tight' ? `впритык: запас ≈${slackMin} мин` : `запас ≈${slackMin} мин`, tone: fit === 'tight' ? 'bad' : 'ok' }}
                time={time(deal.startsAt)}
                stubLabel={`+${hoursStr(deal.hours)} ч`}
                selected={pick === deal.id}
                disabled={Boolean(booked) || book.isPending}
                onClick={() => {
                  if (booked) return;
                  setPick((p) => (p === deal.id ? null : deal.id));
                }}
              />
            ))}
            {items.length > FIRST && (
              <button type="button" className="more-btn" onClick={() => setOpen((o) => !o)}>
                {open ? 'Свернуть' : `Ещё ${rest} ${plural(rest, DEALS)}`}
              </button>
            )}
          </div>
          <div style={{ padding: '8px 24px 0', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            {total >= 2 && <LinkButton onClick={() => navigate(`/route?${query}`)}>Два дела подряд</LinkButton>}
            <LinkButton disabled={company.isPending} onClick={() => company.mutate()}>
              {company.isPending ? 'Собираю компанию…' : 'Пойти компанией: позвать друзей'}
            </LinkButton>
            {company.isError && <div className="error-text center">{errorText(company.error, 'Не получилось создать компанию. Попробуй ещё раз.')}</div>}
          </div>
        </>
      )}

      <div className="spacer" />
      <Footer>
        {picked && booked && (
          <LinkButton onClick={() => navigate(`/deals/${picked.id}${params.from === 'home' ? '?f=home' : ''}`)}>Открыть дело</LinkButton>
        )}
        {!noWindow && (
        <SlideToConfirm
          disabled={!picked}
          disabledLabel="Сначала выбери, куда идёшь"
          label={picked ? `Сдвинь — иду в ${time(picked.startsAt)}` : ''}
          doneLabel={picked ? `Ты идёшь в ${time(picked.startsAt)}` : ''}
          done={Boolean(booked)}
          busy={book.isPending}
          onConfirm={() => picked && book.mutate({ dealId: picked.id }, { onSuccess: setBooked })}
        />
        )}
        {book.isError && <div className="error-text center">{errorText(book.error, 'Не получилось записаться. Попробуй ещё раз.')}</div>}
        {picked && !booked && <div className="meta center">{cancelLine(picked.cancelUntil)}</div>}
        {picked && booked && <div className="meta center">{instructionLine(picked.instructionsAt, false)}</div>}
        {cancel.isError && <div className="error-text center">{errorText(cancel.error, 'Не получилось отменить. Попробуй ещё раз.')}</div>}
        {booked && (
          <LinkButton tone="danger" disabled={cancel.isPending} onClick={() => cancel.mutate(booked, { onSuccess: () => setBooked(null) })}>
            Отменить запись
          </LinkButton>
        )}
      </Footer>
    </Screen>
  );
}
