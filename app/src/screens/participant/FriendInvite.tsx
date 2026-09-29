import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api';
import type { FriendInvite } from '@/api/types';
import { dayWord, hoursStr, time, clean } from '@/lib/format';
import { DemoBadge, ErrorState, Footer, Hero, Loading, PrimaryButton, Screen, Ticket } from '@/ui';
import type { HeroTone } from '@/ui';

const VIEW: Record<FriendInvite['status'], { tone: HeroTone; cta: string }> = {
  ok: { tone: 'blue', cta: 'Открыть дело' },
  full: { tone: 'ink', cta: 'Найти похожее' },
  expired: { tone: 'paper', cta: 'На главную' },
};

export function FriendInviteScreen() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ['friend-invite', token], queryFn: () => api.friendInvite(token), retry: false });

  if (q.isPending) return <Screen><Hero right={<DemoBadge />} /><Loading /></Screen>;
  if (q.isError)
    return (
      <Screen>
        <Hero right={<DemoBadge />} caption="Приглашение" />
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      </Screen>
    );

  const inv = q.data;
  const v = VIEW[inv.status];
  const name = inv.inviterName ?? 'Друг';
  const d = inv.deal;
  const title = inv.status === 'ok' ? `${name} зовёт тебя` : inv.status === 'full' ? 'Мест уже нет' : 'Приглашение устарело';
  const text =
    inv.status === 'ok'
      ? 'Запишись — и пойдёте вместе. Инструкцию пришлю вечером накануне.'
      : inv.status === 'full'
        ? `${name} звал тебя, но все места уже заняли. На это же время есть похожие дела.`
        : 'Смена уже началась или её отменили. Найдём другое дело под твоё время.';

  const go = () => {
    if (inv.status === 'ok' && d) navigate(`/deals/${d.id}?inv=${encodeURIComponent(token)}`, { replace: true });
    else navigate(inv.status === 'full' ? '/search' : '/', { replace: true });
  };

  return (
    <Screen>
      <Hero tone={v.tone} right={<DemoBadge />} caption="Приглашение от друга">
        <div className="hero__main" style={{ paddingBottom: 32 }}>
          <h1 style={{ margin: 0, font: '800 36px/40px var(--font-display)', letterSpacing: -1.5, textWrap: 'pretty' }}>{title}</h1>
        </div>
      </Hero>

      <div className="body body--tight">
        <div className="text">{text}</div>
        {d && (
          <Ticket
            kicker={`${clean(d.org.name)} · ${d.address}`}
            title={d.title}
            lines={[`${dayWord(d.startsAt)} · ${hoursStr(d.hours)} ч · свободно ${Math.max(0, d.capacity - d.taken)} из ${d.capacity}`]}
            time={time(d.startsAt)}
            hotStub={inv.status === 'ok'}
            off={inv.status !== 'ok'}
          />
        )}
      </div>

      <div className="spacer" />
      <Footer>
        <PrimaryButton onClick={go}>{v.cta}</PrimaryButton>
      </Footer>
    </Screen>
  );
}
