import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api';
import type { CoordMicroTask } from '@/api/types';
import { errorText } from '@/lib/errors';
import { ddmm, plural } from '@/lib/format';
import { ErrorState, Footer, Hero, HeroBig, LinkButton, Loading, PrimaryButton, Screen, Strip, Switch } from '@/ui';
import { CoordBadge, useCabinetNav } from './common';

const TASKS: [string, string, string] = ['дело', 'дела', 'дел'];

function line(t: CoordMicroTask) {
  const parts = [`${t.minutes} мин`, `принято ${t.accepted} из ${t.answersNeeded}`];
  if (t.pending) parts.push(`ждут проверки ${t.pending}`);
  if (t.deadline) parts.push(`до ${ddmm(t.deadline)}`);
  return parts.join(' · ');
}

export function MicroTasksScreen() {
  const nav = useCabinetNav();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['coord-micro'], queryFn: api.coordMicroTasks });
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => api.setMicroTaskActive(id, active),
    onSuccess: (t) => qc.setQueryData<CoordMicroTask[]>(['coord-micro'], (list) => list?.map((x) => (x.id === t.id ? t : x))),
  });

  if (q.isPending) return <Screen><Hero nav={nav} right={<CoordBadge />} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={nav} right={<CoordBadge />} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const list = q.data;
  const active = list.filter((t) => t.active).length;
  const pending = list.reduce((s, t) => s + t.pending, 0);

  return (
    <Screen>
      <Hero
        nav={nav}
        right={<CoordBadge />}
        caption="Микро-дела · активны"
        strip={<Strip items={[`всего ${list.length}`, pending ? `ждут проверки ${pending}` : 'проверять нечего']} />}
      >
        <HeroBig value={active} unit={<span style={{ fontSize: 24, lineHeight: '28px', letterSpacing: -0.5 }}>{plural(active, TASKS)}</span>} />
      </Hero>

      <div className="body">
        <section className="stack stack--4">
          {list.length === 0 && (
            <div className="card card--dashed">
              <div className="text">Микро-дел пока нет. Это задания на 5–60 минут, которые студенты делают из дома.</div>
            </div>
          )}
          {list.map((t) => (
            <div key={t.id} className="list-row" style={{ opacity: t.active ? 1 : 0.6 }}>
              <span className="stack stack--4" style={{ minWidth: 0 }}>
                <span className="list-row__title">{t.title}</span>
                <span className="meta">{t.active ? line(t) : `выключено · ${line(t)}`}</span>
              </span>
              <Switch
                checked={t.active}
                label={t.active ? `Выключить: ${t.title}` : `Включить: ${t.title}`}
                onChange={(v) => !toggle.isPending && toggle.mutate({ id: t.id, active: v })}
              />
            </div>
          ))}
          {toggle.isError && <div className="error-text">{errorText(toggle.error, 'Не получилось переключить. Попробуй ещё раз.')}</div>}
          <div className="meta" style={{ paddingTop: 8 }}>
            Выключенное дело пропадает из подбора; ответы, которые уже пришли, остаются на проверке.
          </div>
        </section>
        {pending > 0 && (
          <div className="links-row">
            <LinkButton onClick={() => navigate('/coord/reviews')}>Проверить ответы · {pending}</LinkButton>
          </div>
        )}
      </div>

      <div className="spacer" />
      <Footer>
        <PrimaryButton onClick={() => navigate('/coord/micro/new')}>Новое микро-дело</PrimaryButton>
      </Footer>
    </Screen>
  );
}
