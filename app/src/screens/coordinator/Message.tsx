import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import type { MessageAudience } from '@/api/types';
import { dayWord, time } from '@/lib/format';
import { Chips, ErrorState, FieldGroup, Footer, Hero, HeroTitle, LinkButton, Loading, PrimaryButton, Screen, Sticker, Strip, TextField } from '@/ui';
import { clean, CoordBadge } from './common';

const MAX = 500;
const LABEL: Record<MessageAudience, string> = { all: 'Все', waiting: 'Не отметились', came: 'Пришли' };
const TEMPLATES = ['Вход со двора', 'Начнём на 10 минут позже', 'Возьмите перчатки'];

export function MessageScreen() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [to, setTo] = useState<MessageAudience>('all');
  const [text, setText] = useState('');
  const [err, setErr] = useState(false);

  const shift = useQuery({ queryKey: ['attendance', id], queryFn: () => api.attendance(id) });
  const aud = useQuery({ queryKey: ['audiences', id], queryFn: () => api.audiences(id) });
  const send = useMutation({ mutationFn: () => api.messageParticipants(id, { audience: to, text: text.trim() }) });

  const nav = { label: '‹ Смена', onClick: () => navigate(`/coord/shifts/${id}`) };
  if (aud.isPending) return <Screen><Hero nav={nav} right={<CoordBadge />} /><Loading /></Screen>;
  if (aud.isError) return <Screen><Hero nav={nav} right={<CoordBadge />} /><ErrorState error={aud.error} onRetry={() => aud.refetch()} /></Screen>;

  const names = aud.data.find((a) => a.key === to)?.names ?? [];
  const n = names.length;
  const sent = send.data;
  const s = shift.data?.shift;
  const caption = s ? `${clean(s.title)} · ${dayWord(s.startsAt)} ${time(s.startsAt)}` : 'Смена';

  const submit = () => {
    if (!text.trim()) {
      setErr(true);
      return;
    }
    send.mutate();
  };
  const again = () => {
    send.reset();
    setText('');
  };

  return (
    <Screen>
      <Hero
        nav={nav}
        right={<CoordBadge />}
        tone={sent ? 'orange' : 'blue'}
        caption={caption}
        strip={<Strip items={['Придёт от бота', 'ответы тебе в MAX']} />}
      >
        <HeroTitle
          text={sent ? 'Сообщение ушло' : 'Написать участникам'}
          sticker={
            <Sticker white={Boolean(sent)} style={{ fontSize: 15 }}>
              {sent ? sent.sent : n}
              <br />
              чел.
            </Sticker>
          }
        />
      </Hero>

      {sent ? (
        <>
          <div className="body">
            <section className="stack">
              <h2 className="h2">Что ушло</h2>
              <div className="sent-text">{text}</div>
              <div className="meta">Получили: {names.join(', ')}</div>
              <LinkButton start style={{ marginLeft: -8, padding: '0 8px' }} onClick={again}>
                Написать ещё
              </LinkButton>
            </section>
          </div>
          <div className="spacer" />
          <Footer>
            <PrimaryButton onClick={() => navigate(`/coord/shifts/${id}`)}>К смене</PrimaryButton>
          </Footer>
        </>
      ) : (
        <>
          <div className="body body--tight">
            <FieldGroup label="Кому">
              <Chips<MessageAudience>
                label="Кому"
                options={aud.data.map((a) => ({ value: a.key, label: `${LABEL[a.key]} · ${a.names.length}` }))}
                value={to}
                onChange={(v) => v && setTo(v)}
              />
              <div className="meta">{n ? names.join(', ') : 'В этой группе пока никого нет'}</div>
            </FieldGroup>
            <TextField
              label="Сообщение"
              multiline
              rows={4}
              maxLength={MAX}
              counter
              value={text}
              onChange={(v) => {
                setText(v);
                setErr(false);
              }}
              placeholder="Например: вход со двора, у двери встретит координатор"
              error={err && 'Напиши текст сообщения.'}
            />
            <FieldGroup label="Быстрый текст">
              <div className="chips">
                {TEMPLATES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className="chip chip--dashed"
                    onClick={() => {
                      setText((cur) => `${cur ? `${cur} ` : ''}${t}.`.slice(0, MAX));
                      setErr(false);
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </FieldGroup>
          </div>
          <div className="spacer" />
          <Footer>
            {send.isError && <div className="error-text center">{errorText(send.error, 'Не получилось отправить. Текст сохранён — попробуй ещё раз.')}</div>}
            <PrimaryButton disabled={send.isPending || n === 0} onClick={submit}>
              {send.isPending ? 'Отправляю…' : `Отправить ${n} ${n === 1 ? 'человеку' : 'людям'}`}
            </PrimaryButton>
          </Footer>
        </>
      )}
    </Screen>
  );
}
