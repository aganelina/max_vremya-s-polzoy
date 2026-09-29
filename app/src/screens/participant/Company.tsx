import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api';
import type { Category, Company } from '@/api/types';
import { errorText } from '@/lib/errors';
import { CATEGORIES, CATEGORY_LABEL, DEALS, durationSticker, isNear, minutesBetween, plural, time, travelLabel, weekdayDate, clean } from '@/lib/format';
import { useBooking } from '@/lib/useBooking';
import { closeApp, isBridgeAvailable, shareLink } from '@/max/bridge';
import { canGoBack } from '@/lib/nav';
import { Chips, DemoBadge, ErrorState, Footer, Hero, HeroTimes, LinkButton, Loading, PillButton, Screen, SlideToConfirm, Sticker, TextField, Ticker, Ticket } from '@/ui';
import { SHARED } from '@/lib/share';

type Filter = 'all' | 'near' | Category;
const FIRST = 3;
const SEATS: [string, string, string] = ['место', 'места', 'мест'];

export function CompanyScreen() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['company', id], queryFn: () => api.company(id) });
  const [filter, setFilter] = useState<Filter>('all');
  const [open, setOpen] = useState(false);
  const { book, cancel } = useBooking();

  const refresh = () => qc.invalidateQueries({ queryKey: ['company', id] });
  const [editWin, setEditWin] = useState(false);
  const [winFrom, setWinFrom] = useState('17:30');
  const [winTo, setWinTo] = useState('20:00');
  const [shared, setShared] = useState<string | null>(null);
  const setWindow = useMutation({
    mutationFn: (w: { from: string; to: string } | null) => api.setCompanyWindow(id, w),
    onSuccess: (c) => {
      qc.setQueryData(['company', id], c);
      setEditWin(false);
    },
  });
  const remind = useMutation({ mutationFn: (memberId: string) => api.remind(id, memberId), onSuccess: refresh });
  const pick = useMutation({
    mutationFn: (dealId: string | null) => api.pickCompanyDeal(id, dealId),
    onMutate: (dealId) => {
      const prev = qc.getQueryData<Company>(['company', id]);
      if (prev) qc.setQueryData(['company', id], { ...prev, pickedDealId: dealId });
      return prev;
    },
    onError: (_e, _v, prev) => prev && qc.setQueryData(['company', id], prev),
    onSuccess: (c) => qc.setQueryData(['company', id], c),
  });

  const close = { label: 'Закрыть', onClick: () => (canGoBack() ? navigate(-1) : isBridgeAvailable() ? closeApp() : navigate('/', { replace: true })) };
  if (q.isPending) return <Screen><Hero nav={close} striped /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={close} striped /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const c = q.data;
  const win = c.commonWindow;
  const [durA, durB] = win ? durationSticker(minutesBetween(win.from, win.to)) : ['', ''];
  const all = c.deals.map((x, i) => ({ ...x, num: String(i + 1).padStart(2, '0') }));
  const items = all.filter(({ deal }) => (filter === 'all' ? true : filter === 'near' ? isNear(deal.travelMin, 'campus') : deal.category === filter));
  const shown = open ? items : items.slice(0, FIRST);
  const rest = items.length - shown.length;
  const picked = all.find((x) => x.deal.id === c.pickedDealId)?.deal ?? null;
  const going = picked?.myBooking ?? null;
  const pending = c.members.find((m) => !m.isMe && !m.window) ?? null;
  const withWindow = c.members.filter((m) => m.window);

  const counts = (f: Filter) => all.filter(({ deal }) => (f === 'all' ? true : f === 'near' ? isNear(deal.travelMin, 'campus') : deal.category === f)).length;
  const meMember = c.members.find((m) => m.isMe) ?? null;
  const markWindow = () => {
    const day = new Date(c.date);
    const at = (hm: string) => {
      const [h, m] = hm.split(':').map(Number);
      const d = new Date(day);
      d.setHours(h, m, 0, 0);
      return d.toISOString();
    };
    setWindow.mutate({ from: at(winFrom), to: at(winTo) });
  };
  const copyInvite = async () => setShared(SHARED[await shareLink(c.inviteLink, 'Пойдём на доброе дело вместе — отметь, когда ты свободен')]);
  const filters = (['all', 'near', ...CATEGORIES] as Filter[])
    .map((f) => ({ value: f, label: f === 'all' ? 'Все' : f === 'near' ? 'До 10 мин' : CATEGORY_LABEL[f], count: counts(f) }))
    .filter((f) => f.value === 'all' || f.count > 0);

  const note = pending
    ? pending.remindedAt
      ? `Напомнил: ${pending.firstName} получит сообщение в MAX`
      : `${pending.firstName}: окно ещё не отмечено. Нажми на ${pending.initial} — напомню`
    : 'Все отметили окна — выбирайте, куда идти';

  return (
    <Screen className="screen--company">
      <Hero
        striped
        nav={close}
        right={<DemoBadge />}
        caption={`${weekdayDate(c.date)} · общее окно`}
        captionDot
        strip={
          <Ticker
            items={[
              'Общее окно',
              win ? `${time(win.from)}–${time(win.to)}` : 'окно не найдено',
              withWindow.map((m) => m.firstName).join(' + '),
              pending ? `${pending.firstName} думает` : c.members.length < 2 ? 'ждём друзей' : 'все в деле',
              'Идём вместе',
            ]}
          />
        }
      >
        {win ? (
          <HeroTimes
            from={time(win.from)}
            to={time(win.to)}
            sticker={
              <Sticker style={{ bottom: 'auto', top: 44, right: -4, fontSize: 15, padding: '12px 14px' }}>
                {durA}
                <br />
                {durB}
              </Sticker>
            }
          />
        ) : (
          <div className="hero__main">
            <div className="hero__title">Общего окна пока нет</div>
          </div>
        )}
      </Hero>

      <div className="row" style={{ padding: '18px 20px 0' }}>
        <div style={{ display: 'flex', flexShrink: 0 }}>
          {c.members.map((m, i) => {
            const style = { marginLeft: i ? -10 : 0, transform: `rotate(${[-6, 5, -3][i % 3]}deg)` };
            if (!m.isMe && !m.window)
              return (
                <button
                  key={m.id}
                  type="button"
                  className="avatar avatar--pending"
                  style={style}
                  aria-label={`Напомнить: ${m.firstName}`}
                  disabled={remind.isPending || Boolean(m.remindedAt)}
                  onClick={() => remind.mutate(m.id)}
                >
                  {m.initial}
                </button>
              );
            return (
              <span key={m.id} className={`avatar grad-${m.isMe ? 1 : 2}`} style={{ ...style, marginLeft: i ? -10 : 0 }} title={m.firstName}>
                {m.initial}
              </span>
            );
          })}
        </div>
        <span style={{ fontSize: 13, lineHeight: '17px', fontWeight: 500, color: remind.isError ? 'var(--red)' : 'rgba(6,7,8,.72)', textWrap: 'pretty' }} role="status">
          {remind.isError ? errorText(remind.error, 'Не получилось напомнить. Попробуй ещё раз.') : c.members.length < 2 ? 'Пока ты один. Позови друзей по ссылке' : note}
        </span>
      </div>

      <div className="stack" style={{ padding: '12px 20px 0' }}>
        {meMember && (!meMember.window || editWin) ? (
          <div className="card" style={{ gap: 12 }}>
            <span className="caps">{meMember.window ? 'Твоё окно' : 'Отметь своё окно'}</span>
            <div className="grid-2" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <TextField label="С" type="time" value={winFrom} onChange={setWinFrom} />
              <TextField label="До" type="time" value={winTo} onChange={setWinTo} />
            </div>
            {winTo <= winFrom && <div className="error-text">Конец окна должен быть позже начала.</div>}
            <div className="pair">
              {meMember.window && (
                <PillButton disabled={setWindow.isPending} onClick={() => setEditWin(false)}>
                  Оставить
                </PillButton>
              )}
              <PillButton tone="ink" disabled={setWindow.isPending || winTo <= winFrom} onClick={markWindow}>
                {setWindow.isPending ? 'Сохраняю…' : 'Отметить окно'}
              </PillButton>
            </div>
            {setWindow.isError && <div className="error-text">{errorText(setWindow.error, 'Не получилось сохранить окно. Попробуй ещё раз.')}</div>}
          </div>
        ) : null}
        <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
          {meMember?.window && !editWin && (
            <LinkButton start onClick={() => setEditWin(true)}>
              Моё окно: {time(meMember.window.from)}–{time(meMember.window.to)}
            </LinkButton>
          )}
          <LinkButton start className={shared ? 'btn-link--ok' : undefined} onClick={copyInvite}>
            {shared ?? '+ Позвать друзей'}
          </LinkButton>
        </div>
      </div>

      <div className="row row--between" style={{ padding: '22px 20px 12px' }}>
        <h2 style={{ margin: 0, font: '800 22px/26px var(--font-display)', textTransform: 'uppercase', letterSpacing: -0.5 }}>Куда идём</h2>
        <span className="caps" style={{ letterSpacing: 1, color: 'rgba(6,7,8,.6)' }}>
          {all.length} {plural(all.length, DEALS)}
        </span>
      </div>

      {all.length > FIRST && (
        <div style={{ padding: '0 24px 16px' }}>
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
      )}

      <div className="stack stack--12" style={{ padding: '0 16px' }}>
        {all.length === 0 && (
          <div className="card card--dashed">
            <div className="text">В общее окно ничего не влезает. Попробуйте другой день.</div>
            <LinkButton start onClick={() => navigate('/')}>
              Выбрать время заново
            </LinkButton>
          </div>
        )}
        {shown.map(({ deal, num, votes }) => (
          <Ticket
            key={deal.id}
            kicker={`Слот ${num}${votes.length ? ` · ${votes.join(', ')}` : ''}`}
            title={deal.title}
            lines={[[clean(deal.org.name), travelLabel(deal.travelMin, 'campus'), `${deal.capacity - deal.taken} ${plural(deal.capacity - deal.taken, SEATS)}`].filter(Boolean).join(' · ')]}
            time={time(deal.startsAt)}
            stubLabel={deal.id === c.pickedDealId ? 'ВЫБРАН' : 'СТАРТ'}
            selected={deal.id === c.pickedDealId}
            disabled={Boolean(going) || pick.isPending || book.isPending}
            onClick={() => {
              if (going) return;
              pick.mutate(deal.id === c.pickedDealId ? null : deal.id);
            }}
          />
        ))}
        {items.length > FIRST && (
          <button type="button" className="more-btn" onClick={() => setOpen((o) => !o)}>
            {open ? 'Свернуть' : `Ещё ${rest} ${plural(rest, DEALS)}`}
          </button>
        )}
      </div>

      <div className="spacer" />
      <Footer>
        <SlideToConfirm
          disabled={!picked}
          disabledLabel="Сначала выбери, куда идёшь"
          label={picked ? `Сдвинь — идём в ${time(picked.startsAt)}` : ''}
          doneLabel={picked ? `Вы идёте в ${time(picked.startsAt)}` : ''}
          done={Boolean(going)}
          busy={book.isPending || pick.isPending}
          onConfirm={() => picked && book.mutate({ dealId: picked.id, companyId: c.id }, { onSuccess: refresh })}
        />
        {book.isError && <div className="error-text center">{errorText(book.error, 'Не получилось записаться: мест могло не хватить. Выберите другой слот.')}</div>}
        {pick.isError && <div className="error-text center">{errorText(pick.error, 'Не получилось выбрать слот. Попробуй ещё раз.')}</div>}
        {cancel.isError && <div className="error-text center">{errorText(cancel.error, 'Не получилось отменить. Попробуй ещё раз.')}</div>}
        {going && (
          <>
            <div className="hint center">Чтобы выбрать другое дело, сначала отмени текущую запись.</div>
            <LinkButton tone="danger" disabled={cancel.isPending} onClick={() => cancel.mutate(going, { onSuccess: refresh })}>
              Отменить запись
            </LinkButton>
          </>
        )}
      </Footer>
    </Screen>
  );
}
