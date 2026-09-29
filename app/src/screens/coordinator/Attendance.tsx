import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import type { Participant, Shift } from '@/api/types';
import { cap, dayWord, time } from '@/lib/format';
import { ErrorState, Footer, Hero, HeroTitle, LinkButton, Loading, PillButton, PrimaryButton, Screen, Sticker, Strip } from '@/ui';
import { clean, CoordBadge, QrMark, toBooked, useCabinetNav } from './common';
import { screenBrightness } from '@/max/bridge';

const CAME: Participant['status'][] = ['came', 'late', 'manual'];

function statusLine(p: Participant): { text: string; color: string } {
  const at = p.checkedInAt ? ` · отметка в ${time(p.checkedInAt)}` : '';
  switch (p.status) {
    case 'came':
      return { text: `на месте${at}`, color: 'var(--green)' };
    case 'late':
      return { text: `с опозданием${at}`, color: 'var(--green)' };
    case 'manual':
      return { text: 'отметка вручную', color: 'var(--green)' };
    case 'no_show':
      return { text: 'не пришли на смену', color: 'var(--red)' };
    default:
      return { text: 'в списке, ждём отметку', color: 'var(--muted)' };
  }
}

const POLL_MS = 15_000;
const CHECK_IN_LEAD_MS = 15 * 60_000;

function pollEvery(shift: Shift | undefined): number | false {
  if (!shift || shift.status !== 'open') return false;
  const now = Date.now();
  const from = new Date(shift.startsAt).getTime() - CHECK_IN_LEAD_MS;
  const to = new Date(shift.endsAt).getTime();
  if (now > to) return false;
  return now >= from ? POLL_MS : Math.min(Math.max(POLL_MS, from - now), 3_600_000);
}

export function AttendanceScreen() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const nav = useCabinetNav();
  const [qr, setQr] = useState(false);
  useEffect(() => {
    if (!qr) return;
    screenBrightness.max();
    return () => screenBrightness.restore();
  }, [qr]);
  const [askCancel, setAskCancel] = useState(false);

  const q = useQuery({ queryKey: ['attendance', id], queryFn: () => api.attendance(id), refetchInterval: (query) => pollEvery(query.state.data?.shift) });
  const code = useQuery({
    queryKey: ['checkin-code', id],
    queryFn: () => api.checkInCode(id),
    enabled: qr,
    refetchInterval: 20_000,
  });
  const mark = useMutation({
    mutationFn: ({ pid, on }: { pid: string; on: boolean }) => api.markManual(id, pid, on),
    onSuccess: (data) => qc.setQueryData(['attendance', id], data),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelShift(id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['coord-home'] });
      navigate('/coord', { replace: true });
    },
  });

  if (q.isPending) return <Screen><Hero nav={nav} right={<CoordBadge />} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={nav} right={<CoordBadge />} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const { shift, participants } = q.data;
  const came = participants.filter((p) => CAME.includes(p.status)).length;
  const wait = participants.filter((p) => p.status === 'booked').length;
  const miss = participants.filter((p) => p.status === 'no_show').length;
  const c = code.data?.code;

  return (
    <Screen>
      <Hero
        nav={nav}
        right={<CoordBadge />}
        caption={`${cap(dayWord(shift.startsAt))} ${time(shift.startsAt)}–${time(shift.endsAt)} · ${shift.address}`}
        strip={<Strip items={[`${came} пришли`, `${wait} ждём`, `${miss} не пришли`]} />}
      >
        <HeroTitle
          text={clean(shift.title)}
          sticker={
            <Sticker style={{ fontSize: 15 }}>
              {came}
              <br />
              из {participants.length}
            </Sticker>
          }
        />
      </Hero>

      {qr && (
        <div className="qr-panel" aria-live="polite">
          {code.isError ? (
            <ErrorState text={errorText(code.error, 'Не удалось получить код.')} onRetry={() => code.refetch()} />
          ) : c ? (
            <>
              <QrMark payload={code.data!.qrPayload} />
              <div className="qr-code" aria-label={`Код ${c.split('').join(' ')}`}>
                {c.slice(0, 3)} {c.slice(3)}
              </div>
            </>
          ) : (
            <div className="skeleton" style={{ width: 200, height: 244 }} />
          )}
          <div className="meta">новый код каждую минуту · яркость на максимум</div>
        </div>
      )}

      <div className="body">
        <section className="stack stack--4">
          <h2 className="h2" style={{ paddingBottom: 4 }}>
            Участники
          </h2>
          {participants.map((p) => {
            const s = statusLine(p);
            const busy = mark.isPending && mark.variables?.pid === p.id;
            return (
              <div key={p.id} className="person-row">
                <div className="stack stack--4" style={{ minWidth: 0 }}>
                  <span className="person-row__name">{p.firstName}</span>
                  <span className="meta" style={{ color: s.color }}>
                    {s.text}
                  </span>
                </div>
                {p.status === 'booked' && (
                  <PillButton disabled={busy} onClick={() => mark.mutate({ pid: p.id, on: true })}>
                    Отметить
                  </PillButton>
                )}
                {p.status === 'manual' && (
                  <LinkButton style={{ fontSize: 14 }} disabled={busy} onClick={() => mark.mutate({ pid: p.id, on: false })}>
                    Вернуть
                  </LinkButton>
                )}
              </div>
            );
          })}
          {mark.isError && <div className="error-text">{errorText(mark.error, 'Не получилось сохранить отметку. Попробуй ещё раз.')}</div>}
          <div className="meta" style={{ paddingTop: 8 }}>
            Если кто-то ушёл раньше, поправь время в явке: часы посчитаются по факту.
          </div>
        </section>

        <div className="links-row">
          <LinkButton onClick={() => navigate(`/coord/shifts/${id}/message`)}>Написать участникам</LinkButton>
          {!askCancel && (
            <LinkButton tone="danger" onClick={() => setAskCancel(true)}>
              Отменить смену
            </LinkButton>
          )}
          {askCancel && (
            <div className="card card--danger" style={{ flexBasis: '100%', marginLeft: 8, gap: 12 }} role="alertdialog" aria-label="Отменить смену?">
              <div className="text">
                {toBooked(participants.length)} придёт сообщение об отмене. Вернуть смену будет нельзя.
              </div>
              <div className="pair">
                <PillButton disabled={cancel.isPending} onClick={() => setAskCancel(false)}>
                  Оставить
                </PillButton>
                <PillButton tone="danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
                  {cancel.isPending ? 'Отменяю…' : 'Отменить'}
                </PillButton>
              </div>
              {cancel.isError && <div className="error-text">{errorText(cancel.error, 'Не получилось отменить. Попробуй ещё раз.')}</div>}
            </div>
          )}
        </div>
      </div>

      <div className="spacer" />
      <Footer>
        <PrimaryButton aria-expanded={qr} onClick={() => setQr((v) => !v)}>
          {qr ? 'Скрыть QR' : 'Показать QR для отметки'}
        </PrimaryButton>
      </Footer>
    </Screen>
  );
}
