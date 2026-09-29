import { useNavigate, useParams } from 'react-router-dom';
import { closeApp, isBridgeAvailable, openMaxLink } from '@/max/bridge';
import { DemoBadge, Footer, Hero, HeroTitle, LinkButton, PrimaryButton, Screen, Section, Strip } from '@/ui';

import { botChatLink } from '@/max/bot';

export function OrgInviteScreen() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const botLink = botChatLink(`org_${token}`);

  return (
    <Screen>
      <Hero
        tone="ink"
        right={<DemoBadge />}
        caption="Приглашение координатора"
        strip={<Strip items={['Ссылка на 7 дней', 'работает один раз']} />}
      >
        <HeroTitle text="Тебя зовут в организацию" />
      </Hero>

      <div className="body">
        <Section title="Как принять" gap={8}>
          <ol className="stack" style={{ margin: 0, paddingLeft: 20 }}>
            <li className="text">Открой чат с ботом «Время с пользой».</li>
            <li className="text">Нажми «Начать» — бот примет приглашение и напишет, в какую организацию ты добавлен.</li>
            <li className="text">Вернись сюда: в профиле появится кабинет координатора.</li>
          </ol>
          <div className="meta">Если бот ответил, что ссылка устарела, попроси владельца организации прислать новую.</div>
        </Section>
      </div>

      <div className="spacer" />
      <Footer>
        <PrimaryButton onClick={() => openMaxLink(botLink)}>Открыть чат с ботом</PrimaryButton>
        <LinkButton onClick={() => (isBridgeAvailable() ? closeApp() : navigate('/', { replace: true }))}>Позже</LinkButton>
      </Footer>
    </Screen>
  );
}
