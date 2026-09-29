import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useGoBack } from '@/lib/nav';
import { api, isApiError } from '@/api';
import { errorText } from '@/lib/errors';
import type { MicroTask } from '@/api/types';
import { time } from '@/lib/format';
import { DemoBadge, ErrorState, Footer, Hero, HeroTitle, LinkButton, Loading, PrimaryButton, Screen, Section, SlideToConfirm, Sticker, Strip, TextField } from '@/ui';

const MIN_ANSWER = 10;

export function MicroTaskScreen() {
  const navigate = useNavigate();
  const goBack = useGoBack();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['micro'], queryFn: () => api.nextMicroTask(), retry: (n, e) => !isApiError(e, 'no_micro_tasks') && n < 1 });
  const [answer, setAnswer] = useState('');
  const [empty, setEmpty] = useState(false);
  const [seenId, setSeenId] = useState<string | null>(null);
  if (q.data && q.data.id !== seenId) {
    setSeenId(q.data.id);
    if (q.data.status === 'returned' && q.data.answer) setAnswer(q.data.answer);
  }

  const put = (t: MicroTask) => qc.setQueryData(['micro'], t);
  const reset = () => {
    setAnswer('');
    setEmpty(false);
  };
  const resync = (e: unknown) => {
    if (isApiError(e, 'not_taken', 'already_answered')) void qc.invalidateQueries({ queryKey: ['micro'] });
  };
  const take = useMutation({ mutationFn: (id: string) => api.takeMicroTask(id), onSuccess: put });
  const submit = useMutation({ mutationFn: ({ id, text }: { id: string; text: string }) => api.submitMicroTask(id, text), onSuccess: put, onError: resync });
  const release = useMutation({
    mutationFn: (id: string) => api.releaseMicroTask(id),
    onError: resync,
    onSuccess: () => {
      reset();
      return qc.invalidateQueries({ queryKey: ['micro'] });
    },
  });
  const next = useMutation({
    mutationFn: (skipId: string) => api.nextMicroTask(skipId),
    onSuccess: (t) => {
      reset();
      put(t);
    },
  });

  const back = { label: '‹ Назад', onClick: goBack };
  if (q.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (isApiError(q.error, 'no_micro_tasks') && !q.data)
    return (
      <Screen>
        <Hero nav={back} right={<DemoBadge />} caption="Не выходя из дома" strip={<Strip items={['Новые появятся скоро']} />}>
          <HeroTitle text="Свободных микро-дел пока нет" />
        </Hero>
        <div className="body">
          <div className="text">Все задания уже разобрали или ты их пропустил. Загляни позже — или найди дело под своё окно.</div>
          <LinkButton start onClick={() => navigate('/')}>
            Найти дело рядом
          </LinkButton>
        </div>
      </Screen>
    );
  if (q.isError) return <Screen><Hero nav={back} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const t = q.data;
  const sent = t.status === 'sent' || t.status === 'accepted';
  const taken = t.status === 'taken' || t.status === 'returned';
  const idle = !sent && !taken;

  const send = () => {
    if (answer.trim().length < MIN_ANSWER) {
      setEmpty(true);
      return;
    }
    submit.mutate({ id: t.id, text: answer.trim() });
  };

  return (
    <Screen>
      <Hero
        tone={sent ? 'orange' : 'blue'}
        nav={back}
        right={<DemoBadge />}
        caption={sent ? 'Ответ отправлен' : taken ? `В работе${t.deadline ? ` · ответ до ${time(t.deadline)}` : ''}` : 'Не выходя из дома'}
        strip={<Strip items={[t.org.name, sent ? 'на проверке' : taken ? 'взято тобой' : 'свободно']} />}
      >
        <HeroTitle
          text={t.title}
          sticker={
            <Sticker white={sent}>
              {t.minutes}
              <br />
              мин
            </Sticker>
          }
        />
      </Hero>

      <div className="body body--tight">
        <Section title="Что сделать" gap={8}>
          <div className="text">{t.text}</div>
        </Section>
        {t.status === 'returned' && t.reviewNote && (
          <div className="card card--danger">
            <span className="caps">Что поправить</span>
            <div className="text">{t.reviewNote}</div>
          </div>
        )}
        {taken && (
          <div className="stack">
            <TextField
              label="Твой ответ"
              hint={answer.length ? `${answer.length} знаков` : undefined}
              multiline
              rows={5}
              value={answer}
              placeholder="Можно коротко, в паре предложений"
              onChange={(v) => {
                setAnswer(v);
                setEmpty(false);
              }}
              error={empty && (answer.trim() ? 'Слишком коротко: нужно хотя бы 10 знаков.' : 'Ответ пустой. Напиши хотя бы пару предложений.')}
            />
            {submit.isError && <div className="error-text">{errorText(submit.error, 'Не получилось отправить. Ответ сохранён, попробуй ещё раз.')}</div>}
          </div>
        )}
        {sent && (
          <Section title="Что дальше" gap={8}>
            <div className="text">Организация посмотрит ответ до конца дня. Когда примут, начислю {t.minutes} мин в справку.</div>
          </Section>
        )}
      </div>

      <div className="spacer" />
      <Footer>
        {idle && (
          <>
            <SlideToConfirm label="Сдвинь — беру" doneLabel="Взято" done={false} busy={take.isPending} onConfirm={() => take.mutate(t.id)} />
            {take.isError && <div className="error-text center">{errorText(take.error, 'Не получилось взять дело. Попробуй ещё раз.')}</div>}
            {next.isError && <div className="error-text center">{errorText(next.error, 'Не получилось найти другое дело. Попробуй ещё раз.')}</div>}
            <LinkButton disabled={next.isPending} onClick={() => next.mutate(t.id)}>
              Другое дело
            </LinkButton>
          </>
        )}
        {taken && (
          <>
            <PrimaryButton disabled={submit.isPending} onClick={send}>
              {submit.isPending ? 'Отправляю…' : 'Отправить ответ'}
            </PrimaryButton>
            <LinkButton tone="danger" disabled={release.isPending} onClick={() => release.mutate(t.id)}>
              Вернуть дело
            </LinkButton>
            {release.isError && <div className="error-text center">{errorText(release.error, 'Не получилось вернуть дело. Попробуй ещё раз.')}</div>}
          </>
        )}
        {sent && (
          <>
            <PrimaryButton disabled={next.isPending} onClick={() => next.mutate(t.id)}>
              Взять ещё одно
            </PrimaryButton>
            {next.isError && <div className="error-text center">{errorText(next.error, 'Не получилось найти другое дело. Попробуй ещё раз.')}</div>}
          </>
        )}
      </Footer>
    </Screen>
  );
}
