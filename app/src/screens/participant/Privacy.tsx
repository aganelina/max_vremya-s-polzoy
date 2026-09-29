import { useMutation } from '@tanstack/react-query';
import { useGoBack } from '@/lib/nav';
import { api, hasApiSession } from '@/api';
import { errorText } from '@/lib/errors';
import { DemoBadge, Hero, HeroTitle, LinkButton, Screen, Section, Strip } from '@/ui';

const SECTIONS = [
  { h: 'Что храним', t: 'MAX-id, имя из профиля MAX, вуз, район, интересы, способ передвижения, твои окна, записи и часы.' },
  { h: 'Чего не запрашиваем у участника', t: 'Полное ФИО, телефон, почту и точную геопозицию. Для оценки дороги используем корпус вуза или район и адрес дела.' },
  {
    h: 'Если подключаешь организацию',
    t: 'В заявке сохраняем имя и телефон контактного лица. Для справок можно добавить ФИО и должность подписанта, изображения подписи и печати. Контакты доступны оператору и членам организации; данные подписанта включаются в справки участников.',
  },
  {
    h: 'Кто что видит',
    t: 'Координатор видит имя и статус участников своих смен. Другим студентам показываем инициалы. Статистика показывает только группы от трёх человек.',
  },
  { h: 'Как удалить', t: 'В профиле можно выгрузить свои данные или удалить профиль. При удалении справки аннулируются. Если ты единственный владелец организации, сначала передай права другому участнику.' },
];

export function PrivacyScreen() {
  const goBack = useGoBack();
  const exp = useMutation({ mutationFn: api.exportData });

  return (
    <Screen>
      <Hero
        nav={{ label: '‹ Назад', onClick: goBack }}
        right={<DemoBadge />}
        caption="Политика данных"
        strip={<Strip items={['Окна старше 90 дней удаляются сами']} />}
      >
        <HeroTitle text="Знаем только то, что нужно для подбора">
          <span>Знаем только то, что нужно для подбора</span>
        </HeroTitle>
      </Hero>

      <div className="body" style={{ paddingBottom: 32 }}>
        {SECTIONS.map((s) => (
          <Section key={s.h} title={s.h} gap={8}>
            <div className="text">{s.t}</div>
          </Section>
        ))}
        {hasApiSession() && <div className="stack stack--4" style={{ marginLeft: -8 }}>
          <LinkButton start style={{ padding: '0 8px' }} disabled={exp.isPending || exp.isSuccess} onClick={() => exp.mutate()}>
            {exp.isSuccess ? 'Файл отправлен тебе в чат MAX' : exp.isPending ? 'Готовлю файл…' : 'Выгрузить мои данные'}
          </LinkButton>
          {exp.isError && <div className="error-text" style={{ paddingLeft: 8 }}>{errorText(exp.error, 'Не получилось выгрузить. Попробуй ещё раз.')}</div>}
        </div>}
      </div>
    </Screen>
  );
}
