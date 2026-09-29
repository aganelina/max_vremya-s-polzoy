import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import type { OrgAccess } from '@/api/types';
import { plural, ymd } from '@/lib/format';
import { ErrorState, Hero, HeroTitle, LinkButton, Loading, PillButton, PrimaryButton, Screen, Strip, TextField } from '@/ui';
import { MaxDownloadError, SAVED_LABEL, saveFile } from '@/lib/download';
import { CoordBadge, useCabinetNav } from './common';
import { shareLink } from '@/max/bridge';
import { SHARED } from '@/lib/share';

const COORDS: [string, string, string] = ['координатор', 'координатора', 'координаторов'];
const SHIFTS: [string, string, string] = ['смена', 'смены', 'смен'];

export function AccessScreen() {
  const nav = useCabinetNav();
  const qc = useQueryClient();
  const now = new Date();
  const [from, setFrom] = useState(ymd(new Date(now.getFullYear(), now.getMonth(), 1)));
  const [to, setTo] = useState(ymd(now));
  const [shared, setShared] = useState<string | null>(null);

  const q = useQuery({ queryKey: ['coord-access'], queryFn: api.access });
  const put = (data: OrgAccess) => qc.setQueryData(['coord-access'], data);
  const csv = useMutation({
    mutationFn: () =>
      saveFile({
        name: `yavka_${from}_${to}.csv`,
        fetchLink: () => api.attendanceLink({ from, to }),
        fetchBlob: () => api.exportAttendance({ from, to }),
      }),
  });
  const revoke = useMutation({ mutationFn: ({ id, on }: { id: string; on: boolean }) => api.setCoordinatorRevoked(id, on), onSuccess: put });
  const invite = useMutation({ mutationFn: api.inviteCoordinator, onSuccess: put });
  const [askOwner, setAskOwner] = useState<string | null>(null);
  const owner = useMutation({
    mutationFn: (id: string) => api.transferOwnership(id),
    onSuccess: (data) => {
      put(data);
      setAskOwner(null);
    },
  });

  if (q.isPending) return <Screen><Hero nav={nav} right={<CoordBadge />} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={nav} right={<CoordBadge />} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const a = q.data;
  const active = a.coordinators.filter((c) => !c.revoked).length;
  const iAmOwner = a.coordinators.some((c) => c.me && c.owner);
  const month = now.toLocaleDateString('ru-RU', { month: 'long' });
  const badRange = from > to;

  const copy = async () => {
    if (!a.invite) return;
    setShared(SHARED[await shareLink(a.invite.link, `Приглашение координатором в «${a.orgName}»`)]);
  };

  return (
    <Screen>
      <Hero
        nav={nav}
        right={<CoordBadge />}
        caption={a.orgName}
        strip={<Strip items={[`${active} ${plural(active, COORDS)}`, `${a.shiftsThisMonth} ${plural(a.shiftsThisMonth, SHIFTS)} за ${month}`]} />}
      >
        <HeroTitle text="Выгрузки и доступы" />
      </Hero>

      <div className="body" style={{ paddingBottom: 32 }}>
        <section className="stack stack--12">
          <h2 className="h2">Явка за период</h2>
          <div className="pair">
            <TextField label="С" type="date" value={from} onChange={(v) => { setFrom(v); csv.reset(); }} />
            <TextField label="По" type="date" value={to} onChange={(v) => { setTo(v); csv.reset(); }} />
          </div>
          {badRange && <div className="error-text" role="alert">Дата «с» позже даты «по».</div>}
          <div className="meta">В файле: дата, смена, имя участника, статус, время отметки, начисленные часы.</div>
          <PrimaryButton disabled={csv.isPending || badRange} onClick={() => csv.mutate()}>
            {csv.isPending ? 'Готовлю файл…' : csv.isSuccess ? SAVED_LABEL[csv.data] : 'Выгрузить CSV'}
          </PrimaryButton>
          {csv.isError && (
            <div className="error-text">
              {csv.error instanceof MaxDownloadError
                ? 'MAX не смог скачать файл. Попробуй ещё раз через минуту или открой кабинет в браузере.'
                : errorText(csv.error, 'Не получилось выгрузить. Попробуй ещё раз.')}
            </div>
          )}
        </section>

        <section className="stack stack--4">
          <h2 className="h2" style={{ paddingBottom: 4 }}>
            Координаторы
          </h2>
          {a.coordinators.map((c) =>
            c.owner || c.me || !iAmOwner ? (
              <div key={c.id} className="person-row" style={{ alignItems: 'baseline', minHeight: 0, padding: '12px 0' }}>
                <span className="person-row__name">
                  {c.name}
                  {c.me ? ' · ты' : ''}
                </span>
                <span className="meta">{c.owner ? 'владелец' : c.revoked ? 'доступ отозван' : ''}</span>
              </div>
            ) : (
              <div key={c.id} className="stack stack--4">
                <div className="person-row" style={{ padding: '4px 0' }}>
                  <span className="person-row__name" style={{ opacity: c.revoked ? 0.5 : 1 }}>
                    {c.name}
                    {c.revoked ? ' · доступ отозван' : ''}
                  </span>
                  <span className="row" style={{ gap: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    {!c.revoked && (
                      <LinkButton
                        style={{ fontSize: 14 }}
                        disabled={owner.isPending}
                        onClick={() => {
                          owner.reset();
                          setAskOwner(c.id);
                        }}
                      >
                        Сделать владельцем
                      </LinkButton>
                    )}
                    <LinkButton
                      tone={c.revoked ? undefined : 'danger'}
                      style={{ fontSize: 14 }}
                      disabled={revoke.isPending}
                      onClick={() => revoke.mutate({ id: c.id, on: !c.revoked })}
                    >
                      {c.revoked ? 'Вернуть' : 'Отозвать'}
                    </LinkButton>
                  </span>
                </div>
                {askOwner === c.id && (
                  <div className="card card--danger" role="alertdialog" aria-label="Передать владение">
                    <div className="text">{c.name} станет владельцем, ты — координатором. Отменить сможет только новый владелец.</div>
                    <div className="pair">
                      <PillButton onClick={() => setAskOwner(null)}>Оставить</PillButton>
                      <PillButton tone="danger" disabled={owner.isPending} onClick={() => owner.mutate(c.id)}>
                        {owner.isPending ? 'Передаю…' : 'Передать'}
                      </PillButton>
                    </div>
                    {owner.isError && (
                      <div className="error-text">
                        {errorText(owner.error, 'Не получилось передать владение. Попробуй ещё раз.', {
                          member_not_found: 'Этого координатора уже нет в организации или доступ отозван.',
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ),
          )}
          {revoke.isError && <div className="error-text">{errorText(revoke.error, 'Не получилось изменить доступ.')}</div>}

          {a.invite ? (
            <div className="stack" style={{ paddingTop: 12 }}>
              <div className="invite-box">
                <span className="invite-box__link">{a.invite.link}</span>
                <LinkButton style={{ fontSize: 14 }} onClick={copy}>
                  {shared ?? 'Отправить'}
                </LinkButton>
              </div>
              <div className="meta">Действует 7 дней, работает один раз.</div>
            </div>
          ) : !iAmOwner ? (
            <div className="meta" style={{ paddingTop: 8 }}>Пригласить координатора может владелец организации.</div>
          ) : (
            <LinkButton start style={{ marginLeft: -8, padding: '0 8px' }} disabled={invite.isPending} onClick={() => invite.mutate()}>
              {invite.isPending ? 'Создаю ссылку…' : 'Пригласить координатора'}
            </LinkButton>
          )}
          {invite.isError && <div className="error-text">{errorText(invite.error, 'Не получилось создать приглашение.')}</div>}
        </section>
      </div>
    </Screen>
  );
}
