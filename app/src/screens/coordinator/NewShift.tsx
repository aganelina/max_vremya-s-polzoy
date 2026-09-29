import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import type { Category, NewShift, Shift } from '@/api/types';
import { CATEGORIES, CATEGORY_LABEL, dayWord, hoursStr, minutesBetween, time, ymd } from '@/lib/format';
import { Chips, FieldGroup, Footer, Hero, HeroTitle, LinkButton, PrimaryButton, Screen, Sticker, Strip, Switch, TextField } from '@/ui';
import { CoordBadge, useCabinetNav } from './common';

const TITLE_MAX = 80;
const PLACES: { value: Shift['place']; label: string }[] = [
  { value: 'org', label: 'У организации' },
  { value: 'district', label: 'Выезд в район' },
  { value: 'online', label: 'Онлайн' },
];

const EMPTY: NewShift = {
  title: '',
  date: ymd(new Date(), 1),
  time: '18:00',
  durationMin: 90,
  capacity: 8,
  category: 'ecology',
  place: 'org',
  instructions: '',
  quorum: false,
};

export function NewShiftScreen() {
  const nav = useCabinetNav();
  const qc = useQueryClient();
  const [f, setF] = useState<NewShift>(EMPTY);
  const [titleErr, setTitleErr] = useState(false);
  const [numErr, setNumErr] = useState(false);
  const access = useQuery({ queryKey: ['coord-access'], queryFn: api.access });
  const create = useMutation({
    mutationFn: (p: NewShift) => api.createShift(p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['coord-home'] }),
  });

  const set = <K extends keyof NewShift>(k: K, v: NewShift[K]) => setF((s) => ({ ...s, [k]: v }));
  const done = create.data;
  const hrs = hoursStr(Math.round((done ? minutesBetween(done.startsAt, done.endsAt) : f.durationMin) / 6) / 10);

  const publish = () => {
    const noTitle = !f.title.trim();
    const badNums = f.durationMin < 15 || f.durationMin > 480 || f.capacity < 1 || f.capacity > 200;
    setTitleErr(noTitle);
    setNumErr(badNums);
    if (noTitle || badNums) return;
    create.mutate({ ...f, title: f.title.trim() });
  };
  const again = () => {
    create.reset();
    setF((s) => ({ ...s, title: '' }));
  };

  const caption = done ? `Опубликовано · ${dayWord(done.startsAt)} ${time(done.startsAt)}` : 'Новая смена';
  const title = done ? done.title : f.title || 'Название смены';

  return (
    <Screen className="screen--form">
      <Hero nav={nav} right={<CoordBadge />} tone={done ? 'orange' : 'blue'} caption={caption} strip={<Strip>{access.data?.orgName ?? '…'}</Strip>}>
        <div style={{ opacity: done || f.title ? 1 : 0.5 }}>
          <HeroTitle
            text={title}
            sticker={
              <Sticker white={Boolean(done)}>
                {hrs}
                <br />ч
              </Sticker>
            }
          />
        </div>
      </Hero>

      {done ? (
        <div className="body">
          <section className="stack">
            <h2 className="h2">Что дальше</h2>
            <div className="text">Смену увидят студенты, у которых она влезает в свободное окно. Напишу, когда начнут записываться.</div>
            <LinkButton start style={{ marginLeft: -8, padding: '0 8px' }} onClick={again}>
              Создать ещё одну
            </LinkButton>
          </section>
        </div>
      ) : (
        <div className="body body--tight">
          <div className="stack">
            <TextField
              label="Что делать"
              value={f.title}
              onChange={(v) => {
                set('title', v);
                setTitleErr(false);
              }}
              placeholder="Коротко: что будут делать"
              maxLength={TITLE_MAX}
              counter
              error={titleErr && 'Добавь название: его увидят в списке дел.'}
            />
            <div className="meta">Подробности — в инструкции ниже</div>
          </div>

          <div className="grid-2">
            <TextField label="Дата" type="date" value={f.date} onChange={(v) => set('date', v)} />
            <TextField label="Начало" type="time" value={f.time} onChange={(v) => set('time', v)} />
            <TextField
              label="Длительность, мин"
              type="number"
              value={String(f.durationMin)}
              onChange={(v) => {
                set('durationMin', Math.max(0, Number(v) || 0));
                setNumErr(false);
              }}
            />
            <TextField
              label="Мест"
              type="number"
              value={String(f.capacity)}
              onChange={(v) => {
                set('capacity', Math.max(0, Number(v) || 0));
                setNumErr(false);
              }}
            />
          </div>
          {numErr && (
            <div className="error-text" role="alert" style={{ marginTop: -16 }}>
              Длительность — от 15 минут до 8 часов, мест — от 1 до 200.
            </div>
          )}

          <FieldGroup label="Направление">
            <Chips<Category>
              options={CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABEL[c] }))}
              value={f.category}
              onChange={(v) => v && set('category', v)}
            />
          </FieldGroup>
          <FieldGroup label="Где">
            <Chips<Shift['place']> options={PLACES} value={f.place} onChange={(v) => v && set('place', v)} />
          </FieldGroup>

          <TextField label="Инструкция участнику" multiline rows={3} maxLength={3000} value={f.instructions} onChange={(v) => set('instructions', v)} />

          <div className="switch-row">
            <span className="stack stack--4">
              <span style={{ fontSize: 16, lineHeight: '20px', fontWeight: 700 }}>Собирать по кворуму</span>
              <span className="meta">Все места должны быть заняты к началу. Иначе смена отменится, участникам придёт уведомление.</span>
            </span>
            <Switch checked={f.quorum} onChange={(v) => set('quorum', v)} label="Собирать по кворуму" />
          </div>
        </div>
      )}

      <div className="spacer" />
      {!done && (
        <Footer>
          {create.isError && <div className="error-text center">{errorText(create.error, 'Не получилось опубликовать. Проверь поля и попробуй ещё раз.')}</div>}
          <PrimaryButton disabled={create.isPending} onClick={publish}>
            {create.isPending ? 'Публикую…' : 'Опубликовать смену'}
          </PrimaryButton>
        </Footer>
      )}
    </Screen>
  );
}
