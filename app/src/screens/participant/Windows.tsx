import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useGoBack } from '@/lib/nav';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import type { FreeWindow, SearchParams, WhenSlot } from '@/api/types';
import { cap, durationSticker } from '@/lib/format';
import { toQuery } from '@/lib/searchParams';
import { DemoBadge, ErrorState, Footer, Hero, HeroTimes, LinkButton, Loading, PrimaryButton, Screen, Section, Sticker, Strip } from '@/ui';

const toMin = (hm: string) => {
  const [h, m] = hm.split(':').map(Number);
  return h * 60 + m;
};

function searchFor(w: FreeWindow): SearchParams {
  const len = toMin(w.to) - toMin(w.from);
  const durationMin: SearchParams['durationMin'] = len >= 180 ? 180 : len >= 120 ? 120 : len >= 60 ? 60 : 30;
  const now = new Date();
  const today = now.toLocaleDateString('ru-RU', { weekday: 'long' });
  const tomorrow = new Date(now.getTime() + 86_400_000).toLocaleDateString('ru-RU', { weekday: 'long' });
  const day = w.day.toLowerCase();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const when: WhenSlot =
    day === today ? (nowMin >= toMin(w.from) && nowMin < toMin(w.to) ? 'now' : 'tonight') : day === tomorrow ? 'tomorrow' : 'weekend';
  return { durationMin, when, from: 'campus', window: { from: w.startsAt, to: w.endsAt } };
}

export function WindowsScreen() {
  const navigate = useNavigate();
  const goBack = useGoBack();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['schedule'], queryFn: api.schedule });
  const [pickId, setPickId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (f: File) => api.uploadSchedule(f),
    onSuccess: (s) => qc.setQueryData(['schedule'], s),
  });

  const back = { label: '‹ Назад', onClick: goBack };
  if (q.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={back} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const wins = q.data.windows;
  const w = wins.find((x) => x.id === pickId) ?? wins[0] ?? null;
  const [durA, durB] = w ? durationSticker(toMin(w.to) - toMin(w.from)) : ['', ''];

  return (
    <Screen>
      <Hero
        nav={back}
        right={<DemoBadge />}
        caption={w ? `${w.day} · свободное окно` : 'Свободные окна'}
        captionDot
        strip={<Strip items={[w ? `${cap(w.after)} · ${w.place}` : 'Загрузи расписание — найду окна']} />}
      >
        {w ? (
          <HeroTimes
            from={w.from}
            to={w.to}
            sticker={
              <Sticker style={{ bottom: 'auto', top: 40, right: -4, fontSize: 15, padding: '12px 14px' }}>
                {durA}
                <br />
                {durB}
              </Sticker>
            }
          />
        ) : (
          <div className="hero__main" />
        )}
      </Hero>

      <div className="body">
        <Section title="Окна на неделе" gap={4}>
          {wins.length === 0 && <div className="meta">В расписании нет окон от 60 минут.</div>}
          <div role="radiogroup" aria-label="Окна на неделе">
            {wins.map((x) => {
              const on = x.id === w?.id;
              return (
                <button
                  key={x.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  className="list-row"
                  style={{ gridTemplateColumns: '24px minmax(0,1fr) auto', padding: '8px 0' }}
                  onClick={() => setPickId(x.id)}
                >
                  <span
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: 999,
                      border: '2px solid var(--ink)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <span style={{ width: 12, height: 12, borderRadius: 999, background: on ? 'var(--ink)' : 'transparent' }} />
                  </span>
                  <span className="stack" style={{ gap: 2, minWidth: 0 }}>
                    <span style={{ fontSize: 16, lineHeight: '20px', fontWeight: on ? 700 : 500 }}>{x.day}</span>
                    <span className="meta">{x.after}</span>
                  </span>
                  <span style={{ font: '800 16px/20px var(--font-display)', letterSpacing: -0.5, fontVariantNumeric: 'tabular-nums' }}>
                    {x.from}–{x.to}
                  </span>
                </button>
              );
            })}
          </div>
        </Section>

        <Section title="Расписание" gap={8}>
          <div className="text">
            Загрузи файл календаря из вуза или телефона: пары, работу и другие дела. Свободные окна от 60 минут нахожу между ними.
          </div>
          <div style={{ marginLeft: -8 }}>
            <LinkButton disabled={upload.isPending} onClick={() => fileRef.current?.click()}>
              {upload.isPending ? 'Загружаю…' : q.data.fileName ? `Загружено: ${q.data.fileName}` : 'Загрузить .ics'}
            </LinkButton>
            <input
              ref={fileRef}
              type="file"
              accept=".ics,text/calendar"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = '';
              }}
            />
          </div>
          {upload.isError && <div className="error-text">{errorText(upload.error, 'Не получилось прочитать файл. Нужен календарь в формате .ics.')}</div>}
        </Section>
      </div>

      <div className="spacer" />
      <Footer>
        <PrimaryButton disabled={!w} onClick={() => w && navigate(`/search?${toQuery(searchFor(w))}`)}>
          {w ? `Найти дело на ${w.from}` : 'Найти дело'}
        </PrimaryButton>
      </Footer>
    </Screen>
  );
}
