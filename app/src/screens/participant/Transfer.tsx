import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import { useRefreshDeals } from '@/lib/useBooking';
import type { SeatTransfer } from '@/api/types';
import { dayWord, hoursStr, time, clean } from '@/lib/format';
import { DemoBadge, ErrorState, Footer, Hero, Loading, PrimaryButton, Screen, Ticket } from '@/ui';
import type { HeroTone } from '@/ui';

const VIEW: Record<SeatTransfer['status'], { tone: HeroTone; title: string; cta: string }> = {
  ok: { tone: 'blue', title: 'Место твоё', cta: 'Открыть дело' },
  taken: { tone: 'ink', title: 'Место уже забрали', cta: 'Найти дело' },
  expired: { tone: 'paper', title: 'Ссылка устарела', cta: 'На главную' },
};

export function TransferScreen() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const refresh = useRefreshDeals();
  const q = useQuery({ queryKey: ['transfer', token], queryFn: () => api.seatTransfer(token) });
  const claim = useMutation({
    mutationFn: () => api.claimSeat(token),
    onSuccess: async (b) => {
      await refresh();
      navigate(`/deals/${b.dealId}`, { replace: true });
    },
  });

  if (q.isPending) return <Screen><Hero right={<DemoBadge />} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero right={<DemoBadge />} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const t = q.data;
  const v = VIEW[t.status];
  const d = t.deal;
  const text =
    t.status === 'ok'
      ? `${t.fromName ?? 'Друг'} не сможет прийти и передал тебе своё место. Инструкцию пришлю вечером накануне.`
      : t.status === 'taken'
        ? 'По этой ссылке кто-то успел раньше. На это же время есть похожие дела.'
        : 'Смена уже началась или ссылка скопирована не целиком. Попроси друга прислать её ещё раз.';

  const go = () => {
    if (t.status === 'ok') claim.mutate();
    else navigate(t.status === 'taken' ? '/search' : '/', { replace: true });
  };

  return (
    <Screen>
      <Hero tone={v.tone} right={<DemoBadge />} caption="Передача места">
        <div className="hero__main" style={{ paddingBottom: 32 }}>
          <h1 style={{ margin: 0, font: '800 36px/40px var(--font-display)', letterSpacing: -1.5, textWrap: 'pretty' }}>{v.title}</h1>
        </div>
      </Hero>

      <div className="body body--tight">
        <div className="text">{text}</div>
        {t.status === 'ok' && d && (
          <Ticket
            kicker={`${clean(d.org.name)} · ${d.address}`}
            title={d.title}
            lines={[`${dayWord(d.startsAt)} · ${hoursStr(d.hours)} ч`]}
            time={time(d.startsAt)}
            hotStub
          />
        )}
      </div>

      <div className="spacer" />
      <Footer>
        {claim.isError && (
          <div className="error-text center">{errorText(claim.error, 'Не получилось забрать место. Возможно, его уже заняли — попробуй ещё раз.')}</div>
        )}
        <PrimaryButton disabled={claim.isPending} onClick={go}>
          {claim.isPending ? 'Забираю место…' : v.cta}
        </PrimaryButton>
      </Footer>
    </Screen>
  );
}
