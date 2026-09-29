import { useQuery } from '@tanstack/react-query';
import { api } from '@/api';
import { hoursStr } from '@/lib/format';
import { useNavigate } from 'react-router-dom';
import { DemoBadge, ErrorState, Hero, HeroBig, Loading, Screen, Section, Strip } from '@/ui';
import { CoordBadge, useCabinetNav } from './common';

const pct = (x: number) => `${Math.round(x * 100)}%`;

export function MetricsScreen({ operator }: { operator?: boolean }) {
  const cabinet = useCabinetNav();
  const navigate = useNavigate();
  const nav = operator ? { label: '‹ Заявки', onClick: () => navigate('/operator/orgs') } : cabinet;
  const badge = operator ? <DemoBadge role="ОПЕРАТОР" /> : <CoordBadge />;
  const q = useQuery({ queryKey: [operator ? 'operator-metrics' : 'coord-metrics'], queryFn: operator ? api.operatorMetrics : api.metrics });

  if (q.isPending) return <Screen><Hero nav={nav} right={badge} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={nav} right={badge} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const m = q.data;
  const top = m.funnel[0]?.value || 1;

  return (
    <Screen>
      <Hero
        nav={nav}
        right={badge}
        tone={operator ? 'ink' : 'blue'}
        caption={m.periodLabel}
        strip={<Strip items={[`${m.participants} участников`, `${pct(m.returnedShare)} вернулись`]} />}
      >
        <HeroBig value={hoursStr(m.hours)} unit="ч" />
      </Hero>

      <div className="body" style={{ paddingBottom: 32 }}>
        <Section title="Воронка">
          {m.funnel.map((f) => (
            <div key={f.label} className="stack stack--4">
              <div className="row row--between" style={{ gap: 8 }}>
                <span className="list-row__title">{f.label}</span>
                <span className="num-display">{f.value}</span>
              </div>
              <div
                className="bar"
                role="meter"
                aria-label={f.label}
                aria-valuemin={0}
                aria-valuemax={top}
                aria-valuenow={f.value}
              >
                <div className="bar__fill" style={{ width: `${((f.value / top) * 100).toFixed(1)}%` }} />
              </div>
              <div className="meta">{f.note}</div>
            </div>
          ))}
        </Section>

        <section className="stack stack--4">
          <h2 className="h2" style={{ paddingBottom: 4 }}>
            По организациям
          </h2>
          {m.orgs.length === 0 && <div className="meta">Пока мало данных: строки по группам меньше 3 человек скрыты.</div>}
          {m.orgs.map((o) => (
            <div key={o.name} className="org-row">
              <span className="list-row__title" style={o.name === 'В среднем по пилоту' ? { color: 'var(--muted)' } : undefined}>
                {o.name}
              </span>
              <span className="meta">явка {pct(o.attendance)}</span>
              <span style={{ font: '800 16px/20px var(--font-display)' }}>{hoursStr(o.hours)} ч</span>
            </div>
          ))}
        </section>
      </div>
    </Screen>
  );
}
