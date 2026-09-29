import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api';
import type { NewMicroTask } from '@/api/types';
import { errorCode } from '@/api/errors';
import { errorText } from '@/lib/errors';
import { ddmm, plural, ymd } from '@/lib/format';
import { Chips, FieldGroup, Footer, Hero, HeroTitle, LinkButton, PrimaryButton, Screen, Sticker, Strip, Switch, TextField } from '@/ui';
import { CoordBadge } from './common';

const TITLE_MAX = 120;
const TEXT_MAX = 1000;
const MINUTES = [5, 10, 15, 20, 30, 45, 60].map((v) => ({ value: v, label: `${v} мин` }));
const ANSWERS: [string, string, string] = ['ответ', 'ответа', 'ответов'];

interface Draft {
  title: string;
  text: string;
  minutes: number;
  answersNeeded: number;
  withDeadline: boolean;
  deadlineDate: string;
}

const EMPTY: Draft = { title: '', text: '', minutes: 15, answersNeeded: 10, withDeadline: false, deadlineDate: ymd(new Date(), 14) };

export function NewMicroTaskScreen() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [f, setF] = useState<Draft>(EMPTY);
  const [titleErr, setTitleErr] = useState(false);
  const [textErr, setTextErr] = useState(false);
  const access = useQuery({ queryKey: ['coord-access'], queryFn: api.access });
  const create = useMutation({
    mutationFn: (p: NewMicroTask) => api.createMicroTask(p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['coord-micro'] }),
  });

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => {
    setF((s) => ({ ...s, [k]: v }));
    if (create.isError) create.reset();
  };
  const done = create.data;
  const code = errorCode(create.error);

  const publish = () => {
    const noTitle = !f.title.trim();
    const noText = !f.text.trim();
    setTitleErr(noTitle);
    setTextErr(noText);
    if (noTitle || noText) return;
    create.mutate({
      title: f.title.trim(),
      text: f.text.trim(),
      minutes: f.minutes,
      answersNeeded: f.answersNeeded,
      deadline: f.withDeadline ? new Date(`${f.deadlineDate}T23:59:00`).toISOString() : null,
    });
  };
  const again = () => {
    create.reset();
    setF((s) => ({ ...s, title: '', text: '' }));
  };

  const title = done ? done.title : f.title || 'Название микро-дела';

  return (
    <Screen>
      <Hero
        nav={{ label: '‹ Микро-дела', onClick: () => navigate('/coord/micro') }}
        right={<CoordBadge />}
        tone={done ? 'orange' : 'blue'}
        caption={done ? 'Опубликовано · не выходя из дома' : 'Новое микро-дело'}
        strip={<Strip items={[access.data?.orgName ?? '…', `${f.answersNeeded} ${plural(f.answersNeeded, ANSWERS)}`]} />}
      >
        <div style={{ opacity: done || f.title ? 1 : 0.5 }}>
          <HeroTitle
            text={title}
            sticker={
              <Sticker white={Boolean(done)}>
                {done ? done.minutes : f.minutes}
                <br />
                мин
              </Sticker>
            }
          />
        </div>
      </Hero>

      {done ? (
        <div className="body">
          <section className="stack">
            <h2 className="h2">Что дальше</h2>
            <div className="text">
              Дело увидят студенты в разделе «Не выходя из дома». Ответы придут на проверку — засчитанные {done.minutes} мин попадут в справку.
            </div>
            <div className="pair" style={{ justifyContent: 'flex-start' }}>
              <LinkButton start style={{ marginLeft: -8, padding: '0 8px' }} onClick={again}>
                Создать ещё одно
              </LinkButton>
              <LinkButton onClick={() => navigate('/coord/micro', { replace: true })}>Все микро-дела</LinkButton>
            </div>
          </section>
        </div>
      ) : (
        <div className="body body--tight">
          <div className="stack">
            <TextField
              label="Название"
              value={f.title}
              onChange={(v) => {
                set('title', v);
                setTitleErr(false);
              }}
              placeholder="Подбери 5 книг для подростковой полки"
              maxLength={TITLE_MAX}
              counter
              error={(titleErr && 'Добавь название: его увидят в списке дел.') || (code === 'invalid_title' && errorText(create.error, ''))}
            />
          </div>
          <TextField
            label="Что сделать"
            multiline
            rows={4}
            value={f.text}
            onChange={(v) => {
              set('text', v);
              setTextErr(false);
            }}
            placeholder="Что именно написать или проверить и каким должен быть ответ"
            maxLength={TEXT_MAX}
            counter
            error={(textErr && 'Опиши задание: студент ответит прямо в приложении.') || (code === 'invalid_text' && errorText(create.error, ''))}
          />
          <FieldGroup label="Сколько времени займёт" hint="столько засчитаю">
            <Chips<number> label="Минут" options={MINUTES} value={f.minutes} onChange={(v) => v && set('minutes', v)} />
          </FieldGroup>
          {code === 'invalid_minutes' && <div className="error-text" style={{ marginTop: -16 }}>{errorText(create.error, '')}</div>}
          <FieldGroup label="Сколько ответов нужно">
            <div className="stepper">
              <button type="button" aria-label="Меньше" disabled={f.answersNeeded <= 1} onClick={() => set('answersNeeded', Math.max(1, f.answersNeeded - (f.answersNeeded > 10 ? 5 : 1)))}>
                −
              </button>
              <span className="stepper__value" aria-live="polite">
                {f.answersNeeded}
              </span>
              <button type="button" aria-label="Больше" disabled={f.answersNeeded >= 500} onClick={() => set('answersNeeded', Math.min(500, f.answersNeeded + (f.answersNeeded >= 10 ? 5 : 1)))}>
                +
              </button>
            </div>
            <span className="meta">Наберём столько ответов — дело пропадёт из подбора.</span>
          </FieldGroup>

          <div className="switch-row">
            <span className="stack stack--4">
              <span style={{ fontSize: 16, lineHeight: '20px', fontWeight: 700 }}>Срок</span>
              <span className="meta">{f.withDeadline ? `Принимаю ответы до ${ddmm(`${f.deadlineDate}T12:00:00`)}` : 'Без срока: пока не наберутся ответы'}</span>
            </span>
            <Switch checked={f.withDeadline} onChange={(v) => set('withDeadline', v)} label="Срок" />
          </div>
          {f.withDeadline && (
            <TextField
              label="До какого дня"
              type="date"
              value={f.deadlineDate}
              onChange={(v) => set('deadlineDate', v)}
              error={code === 'deadline_in_past' && errorText(create.error, '')}
            />
          )}
        </div>
      )}

      <div className="spacer" />
      {!done && (
        <Footer>
          {create.isError && !['invalid_title', 'invalid_text', 'invalid_minutes', 'deadline_in_past'].includes(code ?? '') && (
            <div className="error-text center">{errorText(create.error, 'Не получилось опубликовать. Попробуй ещё раз.')}</div>
          )}
          <PrimaryButton disabled={create.isPending} onClick={publish}>
            {create.isPending ? 'Публикую…' : 'Опубликовать микро-дело'}
          </PrimaryButton>
        </Footer>
      )}
    </Screen>
  );
}
