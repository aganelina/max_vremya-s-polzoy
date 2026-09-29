import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import type { UrgentCall } from '@/api/types';
import { time } from '@/lib/format';
import { Chips, FieldGroup, Footer, Hero, HeroTitle, LinkButton, PrimaryButton, Screen, SlideToConfirm, Sticker, Strip, TextField } from '@/ui';
import { CoordBadge, useCabinetNav } from './common';

const STARTS: { value: UrgentCall['startInMin']; label: string }[] = [
  { value: 15, label: '15 мин' },
  { value: 30, label: '30 мин' },
  { value: 45, label: '45 мин' },
  { value: 60, label: '1 ч' },
];

const reachFor = (people: number) => Math.min(40, Math.max(15, people * 3));

export function UrgentScreen() {
  const navigate = useNavigate();
  const nav = useCabinetNav();
  const [what, setWhat] = useState('');
  const [where, setWhere] = useState('');
  const [start, setStart] = useState<UrgentCall['startInMin']>(30);
  const [people, setPeople] = useState(3);
  const [err, setErr] = useState(false);
  const [whereErr, setWhereErr] = useState(false);
  const qc = useQueryClient();
  const call = useMutation({ mutationFn: (p: UrgentCall) => api.urgentCall(p), onSuccess: () => qc.invalidateQueries({ queryKey: ['coord-home'] }) });
  const status = useQuery({
    queryKey: ['urgent', call.data?.id],
    queryFn: () => api.urgentStatus(call.data!.id),
    enabled: Boolean(call.data),
    refetchInterval: 15_000,
  });

  const sent = status.data ?? call.data;
  const reach = reachFor(people);

  const reset = () => {
    call.reset();
    setWhat('');
    setWhere('');
    setWhereErr(false);
  };

  if (sent) {
    const got = sent.responses.length;
    return (
      <Screen>
        <Hero
          nav={nav}
          right={<CoordBadge />}
          tone="ink"
          caption={`Позвали · ${sent.reached} студентов`}
          strip={<Strip items={[`${got} откликнулись`, `ждём ещё ${Math.max(0, sent.people - got)}`]} />}
        >
          <HeroTitle
            text={sent.what || what}
            sticker={
              <Sticker style={{ fontSize: 15 }}>
                {got}
                <br />
                из {sent.people}
              </Sticker>
            }
          />
        </Hero>
        <div className="body">
          <section className="stack stack--4">
            <h2 className="h2" style={{ paddingBottom: 4 }}>
              Откликнулись
            </h2>
            {sent.responses.length === 0 && <div className="meta">Пока никто. Обычно первые отклики — в течение 5 минут.</div>}
            {sent.responses.map((r) => (
              <div key={r.name + r.at} className="list-row" style={{ alignItems: 'baseline', minHeight: 0 }}>
                <span className="list-row__title">{r.name}</span>
                <span className="meta">отклик в {time(r.at)}</span>
              </div>
            ))}
            <div className="meta" style={{ paddingTop: 8 }}>
              Кто откликнется ещё, появится здесь и в смене.
            </div>
          </section>
          <div className="links-row">
            <LinkButton onClick={reset}>Новое срочное дело</LinkButton>
          </div>
        </div>
        <div className="spacer" />
        <Footer>
          <PrimaryButton onClick={() => navigate(`/coord/shifts/${sent.shiftId}`)}>Открыть смену</PrimaryButton>
        </Footer>
      </Screen>
    );
  }

  const ready = Boolean(what.trim() && where.trim());

  return (
    <Screen>
      <Hero
        nav={nav}
        right={<CoordBadge />}
        tone="red"
        caption={`Срочно · начало через ${start === 60 ? '1 ч' : `${start} мин`}`}
        strip={<Strip items={[`до ${reach} студентов`, 'ответ в MAX']} />}
      >
        <HeroTitle
          text="Нужны люди прямо сейчас"
          sticker={
            <Sticker style={{ fontSize: 15 }}>
              {people}
              <br />
              чел.
            </Sticker>
          }
        />
      </Hero>

      <div className="body body--tight">
        <TextField
          label="Что нужно"
          value={what}
          onChange={(v) => {
            setWhat(v);
            setErr(false);
          }}
          maxLength={80}
          placeholder="Помочь разгрузить машину с продуктами"
          error={err && 'Напиши, что нужно сделать: без этого никто не откликнется.'}
        />
        <TextField
          label="Куда прийти и к кому"
          value={where}
          onChange={(v) => {
            setWhere(v);
            setWhereErr(false);
          }}
          maxLength={200}
          placeholder="ул. Декабристов, 85, склад, спросить Рината"
          error={whereErr && 'Напиши адрес: без него не найдут, куда идти.'}
        />
        <FieldGroup label="Начало через">
          <Chips<UrgentCall['startInMin']> options={STARTS} value={start} onChange={(v) => v && setStart(v)} />
        </FieldGroup>
        <FieldGroup label="Сколько человек">
          <div className="stepper">
            <button type="button" aria-label="Меньше" disabled={people <= 1} onClick={() => setPeople((n) => Math.max(1, n - 1))}>
              −
            </button>
            <span className="stepper__value" aria-live="polite">
              {people}
            </span>
            <button type="button" aria-label="Больше" disabled={people >= 30} onClick={() => setPeople((n) => Math.min(30, n + 1))}>
              +
            </button>
          </div>
          {people > 10 && <span className="meta">Для большой группы за 30 минут может не хватить людей. Если время есть, лучше обычная смена.</span>}
        </FieldGroup>
        <section className="stack">
          <h2 className="h2">Кому уйдёт</h2>
          <div className="text">
            Не больше чем {reach} студентам: сначала тем, у кого окно открыто прямо сейчас и кто рядом, потом тем, кто учится или живёт в этом районе.
          </div>
          <div className="meta">Ночью тоже уйдёт — это срочная просьба. Кто не может, просто не ответит.</div>
        </section>
      </div>

      <div className="spacer" />
      <Footer>
        <SlideToConfirm
          label={`Сдвинь — позвать ${people} чел.`}
          doneLabel="Позвали"
          done={false}
          busy={call.isPending}
          disabled={!ready}
          disabledLabel={what.trim() ? 'Сначала напиши, куда прийти' : 'Сначала напиши, что нужно'}
          onDisabledPress={() => {
            setErr(!what.trim());
            setWhereErr(!where.trim());
          }}
          onConfirm={() => call.mutate({ what: what.trim(), where: where.trim(), startInMin: start, people })}
        />
        {call.isError ? (
          <div className="error-text center">{errorText(call.error, 'Не получилось отправить. Попробуй ещё раз.')}</div>
        ) : (
          <div className="meta center" style={{ paddingTop: 4 }}>
            Отменить рассылку уже нельзя
          </div>
        )}
      </Footer>
    </Screen>
  );
}
