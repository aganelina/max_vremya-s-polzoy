import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useGoBack } from '@/lib/nav';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import type { HelpRequest, HourBank } from '@/api/types';
import { hoursStr } from '@/lib/format';
import { Chips, DemoBadge, ErrorState, Footer, Hero, HeroBig, Loading, PillButton, PrimaryButton, Screen, Section, Strip } from '@/ui';

const ASK_HOURS = [
  { value: 0.5, label: '30 мин' },
  { value: 1, label: '1 ч' },
  { value: 2, label: '2 ч' },
];

function myLine(r: HelpRequest): { text: string; color: string } {
  if (r.status === 'closed') return { text: `закрыта · списали ${hoursStr(r.hours)} ч`, color: 'var(--muted)' };
  if (r.status === 'matched') return { text: `${r.when} · ${hoursStr(r.hours)} ч · помощник найден: ${r.helperName}`, color: 'var(--green)' };
  return { text: `${hoursStr(r.hours)} ч · ищем помощника`, color: 'var(--muted)' };
}

export function HourBankScreen() {
  const goBack = useGoBack();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['bank'], queryFn: api.hourBank });
  const put = (b: HourBank) => qc.setQueryData(['bank'], b);

  const [askOpen, setAskOpen] = useState(false);
  const [askText, setAskText] = useState('');
  const [askHours, setAskHours] = useState(1);
  const [askErr, setAskErr] = useState(false);
  const [asked, setAsked] = useState(false);

  const respond = useMutation({ mutationFn: ({ id, on }: { id: string; on: boolean }) => api.respondHelp(id, on), onSuccess: put });
  const confirm = useMutation({
    mutationFn: (id: string) => api.confirmHelp(id),
    onSuccess: (b) => {
      put(b);
      return qc.invalidateQueries({ queryKey: ['me'] });
    },
  });
  const ask = useMutation({
    mutationFn: () => api.askHelp({ text: askText.trim(), hours: askHours }),
    onSuccess: (b) => {
      put(b);
      setAsked(true);
      setAskOpen(false);
      setAskText('');
    },
  });

  const back = { label: '‹ Назад', onClick: goBack };
  if (q.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={back} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const b = q.data;
  const openCount = b.mine.filter((m) => m.status !== 'closed').length;
  const full = openCount >= b.maxOpenRequests;
  const reserved = b.reserved ?? 0;
  const available = Math.max(0, b.balance - reserved);
  const overBalance = askOpen && askHours > available;

  const onAsk = () => {
    if (!askOpen) {
      setAsked(false);
      setAskOpen(true);
      return;
    }
    if (!askText.trim()) {
      setAskErr(true);
      return;
    }
    ask.mutate();
  };

  const hint = askErr
    ? 'Напиши, что нужно'
    : ask.isError
      ? errorText(ask.error, 'Не получилось опубликовать. Попробуй ещё раз.')
      : full
        ? `Уже ${b.maxOpenRequests} открытые просьбы — закрой одну, чтобы попросить ещё`
        : overBalance
          ? reserved > 0
            ? `Доступно ${hoursStr(available)} ч (${hoursStr(reserved)} ч в открытых просьбах) — выбери меньше`
            : `На балансе ${hoursStr(b.balance)} ч — выбери меньше`
          : asked
            ? 'Спишем часы, когда отметишь «Помощь получена»'
            : askOpen
              ? `Увидят в твоём районе. Одновременно до ${b.maxOpenRequests} просьб`
              : `Одновременно можно держать до ${b.maxOpenRequests} просьб`;
  const hintBad = askErr || ask.isError || overBalance;

  return (
    <Screen>
      <Hero
        nav={back}
        right={<DemoBadge />}
        caption="Банк часов · можно потратить"
        strip={
          <Strip
            items={
              reserved > 0
                ? [`доступно ${hoursStr(available)} ч (${hoursStr(reserved)} ч в открытых просьбах)`]
                : ['Не купить', 'только заработать делами']
            }
          />
        }
      >
        <HeroBig value={hoursStr(b.balance)} unit="ч" />
      </Hero>

      <div className="body">
        <Section title="Кому нужна помощь" gap={4}>
          <div>
            {b.others.map((o) => (
              <div key={o.id} className="list-row">
                <div className="stack stack--4" style={{ minWidth: 0 }}>
                  <span className="list-row__title">{o.text}</span>
                  <span className="meta">{o.responded ? 'ты откликнулся · автор напишет в MAX' : `${o.when} · ${hoursStr(o.hours)} ч · ${o.district}`}</span>
                </div>
                <PillButton
                  tone={o.responded ? undefined : 'ink'}
                  disabled={respond.isPending && respond.variables?.id === o.id}
                  onClick={() => respond.mutate({ id: o.id, on: !o.responded })}
                >
                  {o.responded ? 'Отменить' : 'Помогу'}
                </PillButton>
              </div>
            ))}
            {b.others.length === 0 && <div className="meta" style={{ padding: '12px 0' }}>Сейчас в районе никто не просит помощи.</div>}
          </div>
          {respond.isError && <div className="error-text">{errorText(respond.error, 'Не получилось откликнуться. Попробуй ещё раз.')}</div>}
          <div className="meta" style={{ paddingTop: 8 }}>
            Видны просьбы твоего района. Контакты не показываем, общение в MAX.
          </div>
        </Section>

        <Section title="Мои просьбы" gap={4}>
          <div>
            {b.mine.map((r) => {
              const line = myLine(r);
              return (
                <div key={r.id} className="list-row">
                  <div className="stack stack--4" style={{ minWidth: 0 }}>
                    <span className="list-row__title">{r.text}</span>
                    <span className="meta" style={{ color: line.color }}>
                      {line.text}
                    </span>
                  </div>
                  {r.status === 'matched' && (
                    <PillButton disabled={confirm.isPending} onClick={() => confirm.mutate(r.id)}>
                      Помощь получена
                    </PillButton>
                  )}
                </div>
              );
            })}
            {b.mine.length === 0 && <div className="meta" style={{ padding: '12px 0' }}>Пока ни одной просьбы.</div>}
          </div>
          {confirm.isError && <div className="error-text">{errorText(confirm.error, 'Не получилось закрыть просьбу. Попробуй ещё раз.')}</div>}
        </Section>
      </div>

      <div className="spacer" />
      <Footer>
        <div className="meta center" style={hintBad ? { color: 'var(--red)' } : undefined} role={hintBad ? 'alert' : undefined}>
          {hint}
        </div>
        {askOpen && (
          <div className="stack" style={{ paddingBottom: 8 }}>
            <input
              className={`field${askErr ? ' field--error' : ''}`}
              aria-label="Что нужно"
              maxLength={80}
              placeholder="Что нужно, коротко"
              value={askText}
              onChange={(e) => {
                setAskText(e.target.value);
                setAskErr(false);
              }}
            />
            <Chips<number> label="Сколько времени" options={ASK_HOURS} value={askHours} onChange={(v) => v != null && setAskHours(v)} />
          </div>
        )}
        <PrimaryButton disabled={full || overBalance || ask.isPending} onClick={onAsk}>
          {ask.isPending ? 'Публикую…' : asked ? 'Попросить ещё' : askOpen ? 'Опубликовать просьбу' : 'Попросить помощи'}
        </PrimaryButton>
      </Footer>
    </Screen>
  );
}
