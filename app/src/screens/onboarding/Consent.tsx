import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, DEMO_ACTIVE, DEMO_AVAILABLE, enterDemo } from '@/api';
import { errorText } from '@/lib/errors';
import { dayWord, hoursStr, time, clean } from '@/lib/format';
import { DemoBadge, Footer, Hero, LinkButton, PrimaryButton, Screen, Section, Sticker, Strip, Ticket } from '@/ui';

const STEPS = [
  'Скажи, когда ты свободен',
  'Найду дело рядом, которое влезет в это время вместе с дорогой',
  'Если подходящего нет, организации увидят, что в это время есть свободные люди',
];

export function ConsentScreen() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [sp] = useSearchParams();
  const next = sp.get('next');
  const friendToken = next?.startsWith('/i/') ? next.slice(3) : null;
  const transferToken = next?.startsWith('/t/') ? next.slice(3) : null;

  const friend = useQuery({ queryKey: ['friend-invite', friendToken], queryFn: () => api.friendInvite(friendToken!), enabled: Boolean(friendToken), retry: false });
  const transfer = useQuery({ queryKey: ['transfer', transferToken], queryFn: () => api.seatTransfer(transferToken!), enabled: Boolean(transferToken), retry: false });
  const consent = useMutation({
    mutationFn: api.consent,
    onSuccess: (me) => {
      qc.setQueryData(['me'], me);
      navigate(`/welcome/place${next ? `?next=${encodeURIComponent(next)}` : ''}`);
    },
  });

  const link = friend.data?.deal
    ? { name: friend.data.inviterName, status: friend.data.status, deal: friend.data.deal, verb: 'зовёт тебя' }
    : transfer.data?.status === 'ok' && transfer.data.deal
      ? { name: transfer.data.fromName, status: 'ok' as const, deal: transfer.data.deal, verb: 'передаёт тебе место' }
      : null;
  const d = link?.deal;
  const linkNote =
    link?.status === 'full'
      ? 'Места на это дело уже заняли — после двух вопросов подберу похожее.'
      : link?.status === 'expired'
        ? 'Это дело уже началось — после двух вопросов подберу другое.'
        : 'Два вопроса о вузе и районе, и сразу откроется это дело.';

  return (
    <Screen>
      <Hero right={<DemoBadge />} caption="Время с пользой" strip={<Strip items={['Без ФИО', 'без телефона', 'без геопозиции']} />}>
        <div className="hero__main" style={{ paddingBottom: 32 }}>
          <h1 style={{ margin: 0, font: '800 36px/40px var(--font-display)', letterSpacing: -1.5, textWrap: 'pretty', paddingRight: 48 }}>
            Доброе дело в&nbsp;твоё свободное окно
          </h1>
          <Sticker style={{ bottom: 12, fontSize: 14, lineHeight: '17px', padding: '11px 13px' }}>
            с дорогой
            <br />
            вместе
          </Sticker>
        </div>
      </Hero>

      <div className="body">
        {d ? (
          <Section title={`${link.name ?? 'Друг'} ${link.verb}`} gap={8}>
            <Ticket
              kicker={`${clean(d.org.name)} · ${d.address}`}
              title={d.title}
              lines={[`${dayWord(d.startsAt)} · ${hoursStr(d.hours)} ч · свободно ${Math.max(0, d.capacity - d.taken)} из ${d.capacity}`]}
              time={time(d.startsAt)}
              hotStub={link.status === 'ok'}
              off={link.status !== 'ok'}
            />
            <div className="meta">{linkNote}</div>
          </Section>
        ) : (
          <ol className="stack stack--16" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {STEPS.map((t, i) => (
              <li key={i} style={{ display: 'grid', gridTemplateColumns: '32px minmax(0,1fr)', gap: 12, alignItems: 'baseline' }}>
                <span style={{ font: '800 18px/24px var(--font-display)', color: 'var(--orange)' }}>{i + 1}</span>
                <span className="text">{t}</span>
              </li>
            ))}
          </ol>
        )}

        <div className="stack stack--4">
          <div className="caps">Что сохраним</div>
          <div className="text">MAX-id, имя, вуз и район. По мере участия сохраняем настройки, расписание, записи и часы. Выгрузить данные или удалить профиль можно в настройках.</div>
          <LinkButton start style={{ marginLeft: -8, padding: '0 8px' }} onClick={() => navigate('/privacy')}>
            Политика данных
          </LinkButton>
        </div>
      </div>

      <div className="spacer" />
      <Footer>
        {consent.isError && <div className="error-text center">{errorText(consent.error, 'Не получилось сохранить согласие. Попробуй ещё раз.')}</div>}
        <PrimaryButton disabled={consent.isPending} onClick={() => consent.mutate()}>
          Согласен, продолжить
        </PrimaryButton>
        {DEMO_AVAILABLE && !DEMO_ACTIVE && <LinkButton onClick={enterDemo}>Посмотреть демо</LinkButton>}
      </Footer>
    </Screen>
  );
}
