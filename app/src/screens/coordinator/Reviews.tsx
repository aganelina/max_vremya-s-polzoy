import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api';
import { useNavigate } from 'react-router-dom';
import { errorText } from '@/lib/errors';
import { plural } from '@/lib/format';
import { ErrorState, Footer, Hero, HeroBig, LinkButton, Loading, Screen, Strip, TextField, Toast } from '@/ui';
import { CoordBadge, useCabinetNav } from './common';

const ANSWERS: [string, string, string] = ['ответ', 'ответа', 'ответов'];

function splitAnswer(a: string): { num: string; text: string }[] {
  if (/^\s*1\.\s/.test(a)) {
    const parts = a.split(/\s*\d+\.\s+/).filter(Boolean);
    if (parts.length > 1) return parts.map((text, i) => ({ num: String(i + 1), text }));
  }
  return a
    .split(/\n+|(?<=[.!?])\s+(?=[А-ЯЁA-Z])/)
    .filter(Boolean)
    .map((text) => ({ num: '', text }));
}

interface Last {
  id: string;
  name: string;
  verdict: 'accept' | 'return';
}

export function ReviewsScreen() {
  const nav = useCabinetNav();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [backing, setBacking] = useState(false);
  const [note, setNote] = useState('');
  const [noteErr, setNoteErr] = useState(false);
  const [last, setLast] = useState<Last | null>(null);

  const q = useQuery({ queryKey: ['review-queue'], queryFn: api.reviewQueue });
  const refresh = () => qc.invalidateQueries({ queryKey: ['review-queue'] });
  const review = useMutation({
    mutationFn: (v: { id: string; name: string; verdict: Last['verdict']; note?: string }) => api.review(v.id, v.verdict, v.note),
    onSuccess: async (_d, v) => {
      setLast({ id: v.id, name: v.name, verdict: v.verdict });
      setBacking(false);
      setNote('');
      await refresh();
    },
  });
  const undo = useMutation({
    mutationFn: (id: string) => api.undoReview(id),
    onSuccess: async () => {
      setLast(null);
      await refresh();
    },
  });

  if (q.isPending) return <Screen><Hero nav={nav} right={<CoordBadge />} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={nav} right={<CoordBadge />} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const { items, acceptedToday, returnedToday } = q.data;
  const cur = items[0];
  const left = items.length;
  const busy = review.isPending || undo.isPending;

  const onBack = () => {
    if (!backing) {
      setBacking(true);
      return;
    }
    if (!note.trim()) {
      setNoteErr(true);
      return;
    }
    review.mutate({ id: cur.id, name: cur.authorName, verdict: 'return', note: note.trim() });
  };

  return (
    <Screen>
      <Hero
        nav={nav}
        right={<CoordBadge />}
        caption="Микро-дела · ждут проверки"
        strip={<Strip items={[`Засчитано сегодня ${acceptedToday}`, `на доработке ${returnedToday}`]} />}
      >
        <HeroBig value={left} unit={<span style={{ fontSize: 24, lineHeight: '28px', letterSpacing: -0.5 }}>{plural(left, ANSWERS)}</span>} />
      </Hero>

      <div className="body body--tight">
        {cur ? (
          <section className="stack stack--16">
            <div className="stack stack--4">
              <span className="caps">
                {cur.authorName} · {cur.minutes} мин
              </span>
              <h2 className="h2" style={{ textWrap: 'pretty' }}>
                {cur.task}
              </h2>
            </div>
            <div className="answer">
              {splitAnswer(cur.answer).map((p, i) => (
                <div key={i} className="answer__part" style={{ gridTemplateColumns: p.num ? '24px minmax(0,1fr)' : 'minmax(0,1fr)' }}>
                  {p.num && <span className="answer__num">{p.num}</span>}
                  <span>{p.text}</span>
                </div>
              ))}
            </div>
            {backing && (
              <TextField
                label="Что поправить"
                multiline
                rows={3}
                value={note}
                onChange={(v) => {
                  setNote(v);
                  setNoteErr(false);
                }}
                placeholder="Например: добавь ещё два вопроса про поиск работы"
                error={noteErr && 'Напиши, что поправить: автор увидит это в MAX.'}
              />
            )}
          </section>
        ) : (
          <section className="stack">
            <h2 className="h2">Всё проверено</h2>
            <div className="text">Новые ответы придут уведомлением в MAX.</div>
          </section>
        )}
        {last && (
          <Toast
            text={last.verdict === 'accept' ? `${last.name}: засчитано, часы начислены` : `${last.name}: вернули на доработку`}
            action={undo.isPending ? 'Возвращаю…' : 'Вернуть'}
            onAction={() => !undo.isPending && undo.mutate(last.id)}
          />
        )}
        {(review.isError || undo.isError) && (
          <div className="error-text">{errorText(review.error ?? undo.error, 'Не получилось сохранить. Попробуй ещё раз.')}</div>
        )}
        <div className="links-row">
          <LinkButton onClick={() => navigate('/coord/micro')}>Микро-дела организации</LinkButton>
          <LinkButton onClick={() => navigate('/coord/micro/new')}>+ Новое микро-дело</LinkButton>
        </div>
      </div>

      <div className="spacer" />
      {cur && (
        <Footer>
          <div className="pair">
            <button type="button" className="btn-outline" disabled={busy} onClick={onBack}>
              {backing ? 'Отправить' : 'На доработку'}
            </button>
            <button
              type="button"
              className="btn-primary"
              style={{ fontSize: 15 }}
              disabled={busy}
              onClick={() => review.mutate({ id: cur.id, name: cur.authorName, verdict: 'accept' })}
            >
              Засчитать
            </button>
          </div>
        </Footer>
      )}
    </Screen>
  );
}
