import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, isApiError } from '@/api';
import type { Category, Me, NotifyMode, Transport } from '@/api/types';
import { errorText } from '@/lib/errors';
import { UniversityNotice } from '@/ui/UniversityNotice';
import { CATEGORIES, CATEGORY_LABEL, DEALS, TRANSPORT_LABEL, hoursStr, plural } from '@/lib/format';
import { Chips, DemoBadge, ErrorState, FieldGroup, Footer, Hero, LinkButton, Loading, MultiChips, PillButton, PrimaryButton, Screen, Segmented, Sticker, Strip } from '@/ui';

interface Draft {
  universityId: string | null;
  districtId: string | null;
  interests: Category[];
  transport: Transport;
  notify: NotifyMode;
}

const fromMe = (me: Me): Draft => ({
  universityId: me.university?.id ?? null,
  districtId: me.district?.id ?? null,
  interests: me.interests,
  transport: me.transport,
  notify: me.notify,
});

const same = (a: Draft, b: Draft) =>
  a.universityId === b.universityId &&
  a.districtId === b.districtId &&
  a.transport === b.transport &&
  a.notify === b.notify &&
  [...a.interests].sort().join() === [...b.interests].sort().join();

export function ProfileScreen() {
  const navigate = useNavigate();
  const me = useQuery({ queryKey: ['me'], queryFn: api.me });
  const dict = useQuery({ queryKey: ['dictionaries'], queryFn: api.dictionaries, staleTime: Infinity });

  const back = { label: '‹ Назад', onClick: () => navigate('/') };
  if (me.isPending || dict.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (me.isError || dict.isError)
    return (
      <Screen>
        <Hero nav={back} />
        <ErrorState
          onRetry={() => {
            me.refetch();
            dict.refetch();
          }}
        />
      </Screen>
    );
  return <ProfileForm me={me.data} dict={dict.data} back={back} />;
}

function ProfileForm({ me, dict, back }: { me: Me; dict: Awaited<ReturnType<typeof api.dictionaries>>; back: { label: string; onClick: () => void } }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => fromMe(me));
  const [askDelete, setAskDelete] = useState(false);
  const dirty = !same(draft, fromMe(me));
  const set = (p: Partial<Draft>) => {
    setDraft((d) => ({ ...d, ...p }));
    save.reset();
  };

  const save = useMutation({
    mutationFn: () =>
      api.updateProfile({
        universityId: draft.universityId ?? undefined,
        districtId: draft.districtId ?? undefined,
        interests: draft.interests,
        transport: draft.transport,
        notify: draft.notify !== me.notify ? draft.notify : undefined,
      }),
    onSuccess: (m) => {
      qc.setQueryData(['me'], m);
      setDraft(fromMe(m));
      qc.invalidateQueries({ queryKey: ['search'] });
    },
  });
  const exp = useMutation({ mutationFn: api.exportData });
  const del = useMutation({
    mutationFn: api.deleteProfile,
    onSuccess: () => {
      qc.clear();
      navigate('/welcome', { replace: true });
    },
  });

  const uni = dict.universities.find((u) => u.id === draft.universityId)?.name ?? '—';
  const district = dict.districts.find((d) => d.id === draft.districtId)?.name ?? '—';
  const s = me.stats;
  const pauseTo = new Date(me.pauseUntil ?? Date.now() + 7 * 86_400_000).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
  const notifyLine = {
    all: 'Новые дела под твои окна, напоминания и итоги',
    mine: 'Только напоминания о делах, на которые записан',
    pause: `Ничего не присылаю до ${pauseTo}`,
  }[draft.notify];

  const links: [string, string, string][] = [
    ['Свободные окна', 'из твоего расписания', '/windows'],
    ['Банк часов', `${hoursStr(s.bankBalance)} ч можно потратить`, '/bank'],
    ['Наставничество', me.roles.mentorEligible ? 'можно ходить с новичками' : 'доступно после 3 дел', '/mentor'],
    ['Справка о часах', 'PDF для вуза', '/certificate'],
    ['Политика данных', 'что храним и кто видит', '/privacy'],
    me.roles.coordinator
      ? ['Кабинет координатора', 'смены, явка, микро-дела', '/coord']
      : ['Подключить организацию', 'фонд, приют, библиотека — заявка на проверку', '/orgs/apply'],
    ...(me.roles.operator ? [['Заявки организаций', 'проверка оператором', '/operator/orgs'] as [string, string, string]] : []),
  ];

  return (
    <Screen>
      <Hero
        nav={back}
        right={<DemoBadge />}
        caption="Профиль"
        strip={<Strip items={[`${hoursStr(s.hoursYear)} ч`, `${s.deals} ${plural(s.deals, DEALS)}`, district]} />}
      >
        <div className="hero__main">
          <h1 style={{ margin: 0, font: '800 56px/60px var(--font-display)', letterSpacing: -2.5, paddingRight: 84, overflowWrap: 'anywhere' }}>
            {me.firstName}
          </h1>
          <Sticker top style={{ top: 4, fontSize: 14, lineHeight: '17px', padding: '11px 13px' }}>
            {uni}
          </Sticker>
        </div>
      </Hero>

      <div className="body body--tight">
        <FieldGroup label="Вуз" hint="от него считаю дорогу">
          <Chips<string>
            label="Вуз"
            options={dict.universities.map((u) => ({ value: u.id, label: u.name }))}
            value={draft.universityId}
            onChange={(v) => v && set({ universityId: v })}
          />
          <UniversityNotice universityId={draft.universityId} />
        </FieldGroup>
        <FieldGroup label="Район, где живёшь">
          <Chips<string>
            label="Район"
            options={dict.districts.map((d) => ({ value: d.id, label: d.name }))}
            value={draft.districtId}
            onChange={(v) => v && set({ districtId: v })}
          />
        </FieldGroup>
        <FieldGroup label="Интересы" hint="можно несколько">
          <MultiChips<Category>
            label="Интересы"
            options={CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABEL[c] }))}
            value={draft.interests}
            onChange={(v) => set({ interests: v })}
          />
        </FieldGroup>
        <FieldGroup label="Как добираешься">
          <Chips<Transport>
            label="Как добираешься"
            options={(Object.keys(TRANSPORT_LABEL) as Transport[]).map((t) => ({ value: t, label: TRANSPORT_LABEL[t] }))}
            value={draft.transport}
            onChange={(v) => v && set({ transport: v })}
          />
        </FieldGroup>
        <div className="stack">
          <span className="caps">Уведомления</span>
          <Segmented<NotifyMode>
            label="Уведомления"
            options={[
              { value: 'all', label: 'Все' },
              { value: 'mine', label: 'Мои записи' },
              { value: 'pause', label: 'Пауза' },
            ]}
            value={draft.notify}
            onChange={(v) => set({ notify: v })}
          />
          <div className="meta">{notifyLine}</div>
        </div>

        <div className="stack stack--4">
          {links.map(([t, m, to]) => (
            <button key={to} type="button" className="list-row" onClick={() => navigate(to)}>
              <span className="stack" style={{ gap: 2 }}>
                <span className="list-row__title">{t}</span>
                <span className="meta">{m}</span>
              </span>
              <span className="list-row__chev" aria-hidden>
                ›
              </span>
            </button>
          ))}
        </div>

        <div className="stack stack--4">
          <LinkButton start disabled={exp.isPending || exp.isSuccess} onClick={() => exp.mutate()}>
            {exp.isSuccess ? 'Файл отправлен тебе в чат MAX' : exp.isPending ? 'Готовлю файл…' : 'Выгрузить мои данные'}
          </LinkButton>
          {exp.isError && <div className="error-text">{errorText(exp.error, 'Не получилось выгрузить. Попробуй ещё раз.')}</div>}
          {askDelete ? (
            <div className="card card--danger" role="alertdialog" aria-label="Удалить профиль">
              <div className="text">Удалим профиль, окна, записи и {hoursStr(s.hoursYear)} ч. Справку потом не собрать.</div>
              <div className="pair">
                <PillButton onClick={() => setAskDelete(false)}>Оставить</PillButton>
                <PillButton tone="danger" disabled={del.isPending} onClick={() => del.mutate()}>
                  {del.isPending ? 'Удаляю…' : 'Удалить навсегда'}
                </PillButton>
              </div>
              {del.isError &&
                (isApiError(del.error, 'last_owner') ? (
                  <div className="stack stack--4">
                    <div className="error-text">Ты единственный владелец организации. Сначала передай её другому координатору в «Выгрузках и доступах».</div>
                    <LinkButton start onClick={() => navigate('/coord/access')}>
                      Выгрузки и доступы
                    </LinkButton>
                  </div>
                ) : (
                  <div className="error-text">{errorText(del.error, 'Не получилось удалить. Попробуй ещё раз.')}</div>
                ))}
            </div>
          ) : (
            <LinkButton start tone="danger" onClick={() => setAskDelete(true)}>
              Удалить профиль
            </LinkButton>
          )}
        </div>
      </div>

      <div className="spacer" />
      {dirty ? (
        <Footer>
          <PrimaryButton disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Сохраняю…' : 'Сохранить'}
          </PrimaryButton>
          {save.isError && <div className="error-text center">{errorText(save.error, 'Не получилось сохранить. Изменения на месте — попробуй ещё раз.')}</div>}
        </Footer>
      ) : (
        save.isSuccess && (
          <Footer>
            <div className="ok-text center" role="status">
              Сохранено. Подбор учтёт новые интересы
            </div>
          </Footer>
        )
      )}
    </Screen>
  );
}
