import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, isApiError } from '@/api';
import type { OperatorOrg, OrgStatus, VerifyOrg } from '@/api/types';
import { openExternalLink } from '@/max/bridge';
import { errorText } from '@/lib/errors';
import { dayMonth, plural } from '@/lib/format';
import { Chips, DemoBadge, ErrorState, Hero, HeroBig, LinkButton, Loading, PillButton, Screen, Segmented, Strip, TextField } from '@/ui';

const APPS: [string, string, string] = ['заявка', 'заявки', 'заявок'];
const TABS: { value: OrgStatus; label: string }[] = [
  { value: 'pending', label: 'Ждут' },
  { value: 'verified', label: 'Проверены' },
  { value: 'rejected', label: 'Отклонены' },
];

function parsePoint(text: string): { lat: number; lon: number } | null {
  const m = text.trim().match(/^(-?\d{1,3}(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:[.,]\d+)?)$/);
  if (!m) return null;
  const lat = Number(m[1].replace(',', '.'));
  const lon = Number(m[2].replace(',', '.'));
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon };
}

function OrgImage({ id, kind }: { id: string; kind: 'seal' | 'signature' }) {
  const q = useQuery({ queryKey: ['org-image', id, kind], queryFn: () => api.operatorOrgImage(id, kind), staleTime: Infinity });
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!q.data) return;
    const u = URL.createObjectURL(q.data);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [q.data]);
  const label = kind === 'seal' ? 'Печать' : 'Подпись';
  return (
    <figure className="stack stack--4" style={{ margin: 0 }}>
      <div style={{ width: 120, height: 120, border: '2px solid var(--ink)', borderRadius: 12, background: 'var(--white)', display: 'grid', placeItems: 'center', overflow: 'hidden' }}>
        {url ? <img src={url} alt={label} style={{ maxWidth: '100%', maxHeight: '100%' }} /> : <span className="meta">{q.isError ? 'нет файла' : '…'}</span>}
      </div>
      <figcaption className="meta">{label}</figcaption>
    </figure>
  );
}

function OrgCard({ o }: { o: OperatorOrg }) {
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonErr, setReasonErr] = useState(false);
  const [images, setImages] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [point, setPoint] = useState('');
  const [pointErr, setPointErr] = useState<string | false>(false);
  const [districtId, setDistrictId] = useState<string | null>(o.districtId);
  const dict = useQuery({ queryKey: ['dictionaries'], queryFn: api.dictionaries, staleTime: Infinity, enabled: verifying });
  const update = (org: OperatorOrg) => qc.setQueryData<OperatorOrg[]>(['operator-orgs'], (list) => list?.map((x) => (x.id === org.id ? { ...x, ...org, createdByName: x.createdByName } : x)));
  const verify = useMutation({ mutationFn: (p: VerifyOrg) => api.verifyOrg(o.id, p), onSuccess: update });
  const submitVerify = () => {
    const pt = parsePoint(point);
    if (!pt) {
      setPointErr(point.trim() ? 'Не похоже на координаты. Нужно так: 55.7899, 49.1150' : 'Вставь координаты места из Яндекс Карт.');
      return;
    }
    verify.mutate({ ...pt, districtId: districtId ?? undefined });
  };
  const pointServerErr = isApiError(verify.error, 'invalid_point') ? errorText(verify.error, 'Сервер не принял точку. Проверь координаты.') : false;
  const reject = useMutation({ mutationFn: () => api.rejectOrg(o.id, reason.trim()), onSuccess: update });
  const busy = verify.isPending || reject.isPending;
  const err = (pointServerErr ? null : verify.error) ?? reject.error;

  const rows: [string, string][] = [
    ['Адрес', o.address],
    ['ИНН', o.inn ?? 'не указан'],
    ['Контакт', `${o.contactName} · ${o.contactPhone}`],
    ['Подписант', o.signName ? `${o.signName}${o.signPosition ? `, ${o.signPosition}` : ''}` : 'не указан'],
    ['Заявку подал', `${o.createdByName || '—'} · ${dayMonth(o.createdAt)}`],
  ];

  return (
    <article className="card" style={{ gap: 12 }}>
      <div className="stack stack--4">
        <span className="caps">{o.status === 'pending' ? 'ждёт проверки' : o.status === 'verified' ? `проверена ${o.verifiedAt ? dayMonth(o.verifiedAt) : ''}` : 'отклонена'}</span>
        <h2 className="h2" style={{ textWrap: 'pretty' }}>
          {o.name}
        </h2>
      </div>
      <div>
        {rows.map(([k, v]) => (
          <div key={k} className="row row--between" style={{ alignItems: 'baseline', gap: 12, padding: '4px 0' }}>
            <span className="meta">{k}</span>
            <span style={{ textAlign: 'right', fontSize: 14, lineHeight: '20px', fontWeight: 600, overflowWrap: 'anywhere' }}>{v}</span>
          </div>
        ))}
      </div>
      {o.status === 'rejected' && o.rejectReason && <div className="text">Причина: {o.rejectReason}</div>}
      {(o.hasSeal || o.hasSignature) &&
        (images ? (
          <div className="row" style={{ gap: 16 }}>
            {o.hasSignature && <OrgImage id={o.id} kind="signature" />}
            {o.hasSeal && <OrgImage id={o.id} kind="seal" />}
          </div>
        ) : (
          <LinkButton start onClick={() => setImages(true)}>
            Показать {[o.hasSignature && 'подпись', o.hasSeal && 'печать'].filter(Boolean).join(' и ')}
          </LinkButton>
        ))}
      {o.status === 'pending' && (
        <div className="stack">
          {verifying && (
            <div className="stack">
              <div className="stack stack--4">
                <span className="caps">Адрес из заявки</span>
                <span className="text" style={{ fontWeight: 600, overflowWrap: 'anywhere' }}>
                  {o.address || 'не указан'}
                </span>
                {o.address && (
                  <LinkButton start onClick={() => openExternalLink(`https://yandex.ru/maps/?text=${encodeURIComponent(o.address)}`)}>
                    Найти адрес в Яндекс Картах ›
                  </LinkButton>
                )}
              </div>
              <TextField
                label="Точка на карте"
                hint="широта, долгота"
                value={point}
                maxLength={60}
                placeholder="55.7899, 49.1150"
                onChange={(v) => {
                  setPoint(v);
                  setPointErr(false);
                  if (verify.isError) verify.reset();
                }}
                error={pointErr || pointServerErr}
              />
              <div className="meta">В Яндекс Картах нажми на вход в здание и скопируй координаты. По ним участники видят дорогу до дел.</div>
              {dict.data && (
                <div className="stack stack--4">
                  <span className="caps">Район · необязательно</span>
                  <Chips<string>
                    scroll
                    allowNone
                    label="Район"
                    options={dict.data.districts.map((d) => ({ value: d.id, label: d.name }))}
                    value={districtId}
                    onChange={(v) => {
                      setDistrictId(v);
                      if (verify.isError) verify.reset();
                    }}
                  />
                </div>
              )}
              {dict.isError && <div className="error-text">{errorText(dict.error, 'Не загрузился список районов — подтвердить можно и без него.')}</div>}
            </div>
          )}
          {rejecting && (
            <TextField
              label="Причина отказа"
              multiline
              rows={3}
              maxLength={500}
              value={reason}
              onChange={(v) => {
                setReason(v);
                setReasonErr(false);
              }}
              placeholder="Например: не удалось дозвониться по телефону"
              error={reasonErr && 'Напиши причину: владелец увидит её в MAX.'}
            />
          )}
          <div className="pair">
            {rejecting ? (
              <>
                <PillButton disabled={busy} onClick={() => setRejecting(false)}>
                  Назад
                </PillButton>
                <PillButton
                  tone="danger"
                  disabled={busy}
                  onClick={() => {
                    if (!reason.trim()) setReasonErr(true);
                    else reject.mutate();
                  }}
                >
                  {reject.isPending ? 'Отклоняю…' : 'Отклонить'}
                </PillButton>
              </>
            ) : verifying ? (
              <>
                <PillButton disabled={busy} onClick={() => setVerifying(false)}>
                  Назад
                </PillButton>
                <PillButton tone="ink" disabled={busy} onClick={submitVerify}>
                  {verify.isPending ? 'Подтверждаю…' : 'Подтвердить'}
                </PillButton>
              </>
            ) : (
              <>
                <PillButton disabled={busy} onClick={() => setRejecting(true)}>
                  Отклонить
                </PillButton>
                <PillButton tone="ink" disabled={busy} onClick={() => setVerifying(true)}>
                  Подтвердить…
                </PillButton>
              </>
            )}
          </div>
        </div>
      )}
      {err && <div className="error-text">{errorText(err, 'Не получилось сохранить решение. Попробуй ещё раз.')}</div>}
    </article>
  );
}

export function OperatorOrgsScreen() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<OrgStatus>('pending');
  const q = useQuery({ queryKey: ['operator-orgs'], queryFn: () => api.operatorOrgs() });

  const nav = { label: '‹ Профиль', onClick: () => navigate('/profile') };
  const badge = <DemoBadge role="ОПЕРАТОР" />;
  if (q.isPending) return <Screen><Hero tone="ink" nav={nav} right={badge} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero tone="ink" nav={nav} right={badge} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const all = q.data;
  const count = (s: OrgStatus) => all.filter((o) => o.status === s).length;
  const pending = count('pending');
  const list = all.filter((o) => o.status === tab);

  return (
    <Screen>
      <Hero
        tone="ink"
        nav={nav}
        right={badge}
        caption="Заявки организаций · ждут проверки"
        strip={<Strip items={[`проверено ${count('verified')}`, `отклонено ${count('rejected')}`]} />}
      >
        <HeroBig value={pending} unit={<span style={{ fontSize: 24, lineHeight: '28px', letterSpacing: -0.5 }}>{plural(pending, APPS)}</span>} />
      </Hero>

      <div className="body" style={{ paddingBottom: 32 }}>
        <Segmented<OrgStatus> label="Какие заявки" options={TABS.map((t) => ({ ...t, label: `${t.label} ${count(t.value)}` }))} value={tab} onChange={setTab} />
        <div className="stack stack--12">
          {list.length === 0 && (
            <div className="card card--dashed">
              <div className="text">{tab === 'pending' ? 'Новых заявок нет. Владельцы получат ответ в MAX сразу после решения.' : 'Здесь пока пусто.'}</div>
            </div>
          )}
          {list.map((o) => (
            <OrgCard key={o.id} o={o} />
          ))}
        </div>
        <LinkButton start onClick={() => navigate('/operator/metrics')}>
          Метрики пилота по всем организациям ›
        </LinkButton>
      </div>
    </Screen>
  );
}
