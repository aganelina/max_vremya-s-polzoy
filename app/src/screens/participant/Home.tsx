import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api';
import type { Origin, SearchParams, WhenSlot } from '@/api/types';
import { DURATION_LABEL, WHEN_LABEL, DEALS, hoursStr, plural } from '@/lib/format';
import { lastSearch, rememberSearch, toQuery, useSearchState } from '@/lib/searchParams';
import { Checkbox, Chips, FieldGroup, Footer, Hero, HeroBig, LinkButton, PrimaryButton, Screen, Sticker, Strip } from '@/ui';

const NEED: Record<SearchParams['durationMin'], string> = { 30: '30 мин', 60: '1 ч', 120: '2 ч', 180: '3 ч' };
const BIG: Record<SearchParams['durationMin'], [string, string]> = { 30: ['0,5', 'ч'], 60: ['1', 'ч'], 120: ['2', 'ч'], 180: ['3+', 'ч'] };

export function HomeScreen() {
  const navigate = useNavigate();
  const { params, set } = useSearchState();
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ['me'], queryFn: api.me });
  const weekly = useMutation({
    mutationFn: (on: boolean) => api.setWeeklySearch(on ? { ...params, companyId: undefined } : null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  });
  const weeklyOn = weekly.isPending ? Boolean(weekly.variables) : Boolean(me.data?.weeklySearch);
  const preview = useQuery({ queryKey: ['search-preview', params], queryFn: () => api.searchPreview(params), placeholderData: (p) => p });

  const n = preview.data?.count;
  const busy = preview.data?.windowSource === 'none';
  const [big, unit] = BIG[params.durationMin];
  const from = params.from === 'home' ? 'рядом с домом' : 'рядом с вузом';

  const go = () => {
    rememberSearch(params);
    navigate(`/search?${toQuery(params)}`);
  };
  const last = lastSearch();

  return (
    <Screen className="screen--home">
      <Hero
        nav={{ label: 'Профиль', onClick: () => navigate('/profile') }}
        right={
          <button type="button" className="hero__nav" onClick={() => navigate('/my')}>
            Мои дела
            <span className="badge" style={{ color: 'var(--orange)', fontFamily: 'var(--font-display)', fontWeight: 800, padding: '4px 8px' }}>
              {me.data ? `${hoursStr(me.data.stats.hoursYear)} ч` : '…'}
            </span>
          </button>
        }
        caption="У меня есть"
        strip={
          <Strip>
            {busy ? (
              <span>
                в расписании нет свободных {NEED[params.durationMin]} {WHEN_LABEL[params.when].toLowerCase()}
              </span>
            ) : (
              <>
                <span className="strip__num">{n ?? '…'}</span>
                <span>{n != null ? `${plural(n, DEALS)} ${from} влезают в окно` : 'считаю дела…'}</span>
              </>
            )}
          </Strip>
        }
      >
        <HeroBig
          value={big}
          unit={unit}
          sticker={
            <Sticker top style={{ top: -30, right: -4, transform: 'rotate(6deg)', fontSize: 12, lineHeight: '16px', padding: '8px 12px' }}>
              + дорога
            </Sticker>
          }
        />
      </Hero>

      <div className="body body--tight">
        <FieldGroup label="Сколько времени">
          <Chips<SearchParams['durationMin']>
            label="Сколько времени"
            options={([30, 60, 120, 180] as const).map((v) => ({ value: v, label: DURATION_LABEL[v] }))}
            value={params.durationMin}
            onChange={(v) => v && set({ durationMin: v })}
          />
        </FieldGroup>
        <FieldGroup label="Когда">
          <Chips<WhenSlot>
            label="Когда"
            options={(Object.keys(WHEN_LABEL) as WhenSlot[]).map((v) => ({ value: v, label: WHEN_LABEL[v] }))}
            value={params.when}
            onChange={(v) => v && set({ when: v })}
          />
        </FieldGroup>
        <FieldGroup label="Откуда идёшь">
          <Chips<Origin>
            label="Откуда идёшь"
            options={[
              { value: 'campus', label: 'От вуза' },
              { value: 'home', label: 'От дома' },
            ]}
            value={params.from}
            onChange={(v) => v && set({ from: v })}
          />
        </FieldGroup>
        <div style={{ marginTop: -8 }}>
          <Checkbox checked={weeklyOn} onChange={(v) => weekly.mutate(v)}>
            Искать под это окно каждую неделю
          </Checkbox>
          {weekly.isError && <div className="error-text">Не получилось сохранить. Попробуй ещё раз.</div>}
        </div>
      </div>

      <div className="spacer" />
      <Footer>
        <PrimaryButton onClick={go}>Найти дело</PrimaryButton>
        <div className="pair">
          <LinkButton disabled={!last} onClick={() => last && set(last)}>
            Как в прошлый раз
          </LinkButton>
          <LinkButton onClick={() => navigate('/micro')}>Не выходя из дома</LinkButton>
        </div>
      </Footer>
    </Screen>
  );
}
