import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useGoBack } from '@/lib/nav';
import { api } from '@/api';
import type { CheckInResult } from '@/api/types';
import { dayWord, hoursStr, time, clean } from '@/lib/format';
import { errorText } from '@/lib/errors';
import { hasCodeReader, haptics, openCodeReader } from '@/max/bridge';
import { DemoBadge, ErrorState, Footer, Hero, HeroTitle, LinkButton, Loading, Screen, Section, Sticker, Strip } from '@/ui';

const ERRORS: Record<NonNullable<CheckInResult['error']>, string> = {
  expired: 'Код устарел: он меняется каждую минуту. Попроси координатора показать новый.',
  wrong_code: 'Код не подходит. Проверь цифры под QR у координатора.',
  too_early: 'Отметиться можно за 15 минут до начала.',
  too_late: 'Отметка уже закрыта. Скажи координатору: он отметит вручную.',
};

type Detector = { detect: (src: ImageBitmap) => Promise<{ rawValue: string }[]> };

const codeFromQr = (raw: string | null | undefined) => raw?.trim().match(/(\d{6})$/)?.[1] ?? null;

async function readQr(file: File): Promise<string | null> {
  const Ctor = (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => Detector }).BarcodeDetector;
  if (!Ctor) return null;
  try {
    const codes = await new Ctor({ formats: ['qr_code'] }).detect(await createImageBitmap(file));
    return codeFromQr(codes[0]?.rawValue);
  } catch {
    return null;
  }
}

export function CheckInScreen() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const goBack = useGoBack();
  const qc = useQueryClient();
  const [sp] = useSearchParams();
  const from = sp.get('f') === 'home' ? 'home' : undefined;
  const q = useQuery({ queryKey: ['deal', id, from], queryFn: () => api.deal(id, from) });
  const [code, setCode] = useState('');
  const [scanMsg, setScanMsg] = useState<string | null>(null);
  const camRef = useRef<HTMLInputElement>(null);

  const booking = q.data?.myBooking ?? null;
  const check = useMutation({
    mutationFn: (c: string) => api.checkIn(booking!.id, c),
    onSuccess: (r) => {
      haptics.notification(r.ok ? 'success' : 'error');
      if (r.ok) qc.invalidateQueries({ queryKey: ['deal', id] });
    },
  });
  const undo = useMutation({
    mutationFn: () => api.undoCheckIn(booking!.id),
    onSuccess: () => {
      check.reset();
      setCode('');
      return qc.invalidateQueries({ queryKey: ['deal', id] });
    },
  });

  const back = { label: '‹ Назад', onClick: goBack };
  if (q.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={back} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const d = q.data;
  const short = clean(d.title).split(' ').slice(0, 2).join(' ');
  const caption = `${short} · ${dayWord(d.startsAt)} ${time(d.startsAt)}`;

  if (!booking) {
    return (
      <Screen>
        <Hero nav={back} right={<DemoBadge />} caption={caption} strip={<Strip items={['Отметка только для записавшихся']} />}>
          <HeroTitle text="Ты не записан на это дело" />
        </Hero>
        <div className="state">
          <div className="text">Сначала запишись — тогда здесь можно будет отметиться на месте.</div>
          <LinkButton onClick={() => navigate(`/deals/${d.id}${from ? '?f=home' : ''}`)}>Открыть дело</LinkButton>
        </div>
      </Screen>
    );
  }

  const manual = !check.data?.ok && booking.status === 'manual';
  const checkedAt = check.data?.ok ? check.data.checkedInAt : booking.status === 'checked_in' || manual ? booking.checkedInAt : null;
  const ok = Boolean(checkedAt) || manual;
  const err =
    check.data && !check.data.ok
      ? ERRORS[check.data.error ?? 'wrong_code']
      : check.isError
        ? errorText(check.error, 'Не получилось отправить код. Проверь интернет.')
        : null;
  const late = check.data?.ok && check.data.late;

  const scan = async () => {
    if (!hasCodeReader()) {
      camRef.current?.click();
      return;
    }
    const raw = await openCodeReader(true);
    if (raw == null) return;
    const found = codeFromQr(raw);
    if (found) {
      setScanMsg(null);
      onCode(found);
    } else setScanMsg('Это не QR смены. Наведи на QR координатора или введи 6 цифр под ним.');
  };

  const onCode = (v: string) => {
    const digits = v.replace(/\D/g, '').slice(0, 6);
    setCode(digits);
    if (check.data || check.isError) check.reset();
    if (digits.length === 6) check.mutate(digits);
  };

  return (
    <Screen>
      <Hero
        tone={ok ? 'orange' : 'blue'}
        nav={back}
        right={<DemoBadge />}
        caption={caption}
        strip={<Strip items={[ok ? 'Координатор видит тебя в списке' : 'QR у координатора · новый каждую минуту']} />}
      >
        <HeroTitle
          text={manual ? 'Координатор отметил тебя вручную' : ok ? `Ты на месте. Отметка в ${time(checkedAt!)}` : 'Отметься, когда придёшь'}
          sticker={
            <Sticker white={ok}>
              +{hoursStr(d.hours)}
              <br />ч
            </Sticker>
          }
        />
      </Hero>

      {ok ? (
        <div className="body">
          <Section title="Что дальше" gap={8}>
            <div className="text">Часы начислю после окончания смены, в {time(d.endsAt)}. Они сразу попадут в справку.</div>
            {late && <div className="meta">Отметка позже начала — координатор увидит «опоздал». На часы это не влияет.</div>}
            <div className="meta">Если уйдёшь раньше, скажи координатору: он поправит время.</div>
          </Section>
        </div>
      ) : (
        <div className="body body--tight">
          <button
            type="button"
            onClick={() => void scan()}
            disabled={check.isPending}
            style={{
              position: 'relative',
              aspectRatio: '1',
              width: '100%',
              border: 0,
              borderRadius: 24,
              background: 'var(--ink)',
              color: 'var(--white)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              overflow: 'hidden',
            }}
          >
            {(['tl', 'tr', 'bl', 'br'] as const).map((c) => (
              <span
                key={c}
                aria-hidden
                style={{
                  position: 'absolute',
                  width: 40,
                  height: 40,
                  [c[0] === 't' ? 'top' : 'bottom']: 32,
                  [c[1] === 'l' ? 'left' : 'right']: 32,
                  [c[0] === 't' ? 'borderTop' : 'borderBottom']: '4px solid var(--orange)',
                  [c[1] === 'l' ? 'borderLeft' : 'borderRight']: '4px solid var(--orange)',
                  borderRadius: { tl: '12px 0 0 0', tr: '0 12px 0 0', bl: '0 0 0 12px', br: '0 0 12px 0' }[c],
                }}
              />
            ))}
            <span style={{ font: '800 18px/24px var(--font-display)' }}>{check.isPending ? 'Проверяю…' : 'Открыть камеру'}</span>
            <span style={{ fontSize: 14, lineHeight: '20px', color: 'rgba(255,255,255,.72)' }}>наведи на QR координатора</span>
          </button>
          <input
            ref={camRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (!f) return;
              const found = await readQr(f);
              if (found) {
                setScanMsg(null);
                onCode(found);
              } else setScanMsg('Не получилось распознать QR. Введи 6 цифр под ним.');
            }}
          />
          {scanMsg && <div className="error-text center">{scanMsg}</div>}

          <div className="stack">
            <div className="caps center">Или 6 цифр под QR</div>
            <label style={{ position: 'relative', display: 'flex', justifyContent: 'center', gap: 8, cursor: 'text' }}>
              {Array.from({ length: 6 }, (_, i) => (
                <span
                  key={i}
                  aria-hidden
                  style={{
                    width: 44,
                    height: 52,
                    borderRadius: 12,
                    border: `2px solid ${err ? 'var(--red)' : 'var(--ink)'}`,
                    background: code[i] || i === code.length ? 'var(--white)' : 'transparent',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    font: '800 20px var(--font-display)',
                  }}
                >
                  {code[i] ?? ''}
                </span>
              ))}
              <input
                value={code}
                onChange={(e) => onCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                aria-label="Код из 6 цифр"
                aria-invalid={Boolean(err)}
                disabled={check.isPending}
                style={{ position: 'absolute', inset: 0, opacity: 0, border: 0, fontSize: 16, caretColor: 'transparent' }}
              />
            </label>
            {err && (
              <div className="error-text center" role="alert">
                {err}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="spacer" />
      <Footer>
        {manual ? null : ok ? (
          <LinkButton disabled={undo.isPending} onClick={() => undo.mutate()}>
            Отметка ошибочная
          </LinkButton>
        ) : (
          <div className="meta center">
            Отметиться можно с {time(d.checkInFrom)} до {time(d.checkInTo)}
          </div>
        )}
        {undo.isError && <div className="error-text center">{errorText(undo.error, 'Не получилось снять отметку. Попробуй ещё раз.')}</div>}
      </Footer>
    </Screen>
  );
}
