import { DEMO_AVAILABLE, enterDemo } from '@/api';
import { botChatLink, registrationPayload } from '@/max/bot';
import { openMaxLink } from '@/max/bridge';
import { Footer, Hero, HeroTitle, LinkButton, PrimaryButton, Screen, Section, Sticker, Strip } from '@/ui';

export function EntryScreen({ expired = false, startRoute = null }: { expired?: boolean; startRoute?: string | null }) {
  return (
    <Screen>
      <Hero caption="Время с пользой" strip={<Strip items={['Добрые дела рядом', 'под твоё время']} />}>
        <HeroTitle text="Доброе дело в твоё свободное окно" sticker={<Sticker>с дорогой<br />вместе</Sticker>} />
      </Hero>
      <div className="body">
        <Section title="Начни с MAX" gap={8}>
          <div className="text">Выбери вуз и район, найди дело под свободное время и запишись. Бот напомнит о встрече и поможет связаться с координатором.</div>
          <div className="meta">Для участия нужна регистрация через MAX. Телефон и полное имя не запрашиваем.</div>
          {expired && <div className="error-text" role="status">Сессия завершилась. Открой приложение из бота ещё раз.</div>}
        </Section>
        {DEMO_AVAILABLE && <Section title="Сначала посмотреть" gap={8}><div className="text">Посмотри, как всё устроено, без регистрации. В демо можно попробовать запись на событие и работу куратора — настоящие записи и сообщения это не затронет.</div></Section>}
      </div>
      <div className="spacer" />
      <Footer>
        <PrimaryButton onClick={() => openMaxLink(botChatLink(registrationPayload(startRoute)))}>Зарегистрироваться через MAX</PrimaryButton>
        {DEMO_AVAILABLE && <LinkButton onClick={enterDemo}>Посмотреть демо</LinkButton>}
      </Footer>
    </Screen>
  );
}
