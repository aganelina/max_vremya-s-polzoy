import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useGoBack } from '@/lib/nav';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import { cancelLine, cap, dayWord, hoursStr, instructionLine, time, travelLabel, clean } from '@/lib/format';
import { useBooking } from '@/lib/useBooking';
import { savePublicFile } from '@/lib/download';
import { SHARED } from '@/lib/share';
import { openMaxLink, shareLink } from '@/max/bridge';
import { botChatLink } from '@/max/bot';
import { Avatar, DemoBadge, ErrorState, Footer, Hero, HeroTitle, LinkButton, Loading, Screen, Section, SlideToConfirm, Sticker, Strip } from '@/ui';

export function DealScreen() {
  const { id = '' } = useParams();
  const [sp] = useSearchParams();
  const inviteToken = sp.get('inv') ?? undefined;
  const from = sp.get('f') === 'home' ? 'home' : undefined;
  const navigate = useNavigate();
  const goBack = useGoBack();
  const q = useQuery({ queryKey: ['deal', id, from], queryFn: () => api.deal(id, from) });
  const { book, cancel } = useBooking();
  const [invited, setInvited] = useState<string | null>(null);
  const invite = useMutation({
    mutationFn: () => api.inviteLink(id),
    onSuccess: async ({ link }) => {
      const r = await shareLink(link, `Пойдём вместе: ${clean(q.data?.title ?? 'доброе дело')}`);
      setInvited(SHARED[r]);
    },
  });
  const calendar = useMutation({
    mutationFn: async () => savePublicFile('delo.ics', (await api.addToCalendar(id)).icsUrl),
  });
  const [transferCopied, setTransferCopied] = useState<string | null>(null);
  const transfer = useMutation({
    mutationFn: (bookingId: string) => api.transferLink(bookingId),
    onSuccess: async ({ link }) => {
      const r = await shareLink(link, `Не смогу прийти — забирай моё место: ${clean(q.data?.title ?? '')}`);
      setTransferCopied(r === 'failed' ? link : `${SHARED[r]} Место твоё, пока друг его не заберёт`);
    },
  });

  const back = { label: '‹ Назад', onClick: goBack };
  if (q.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (q.isError) return <Screen><Hero nav={back} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></Screen>;

  const d = q.data;
  const going = d.myBooking;
  const free = d.capacity - d.taken;
  const seats = Array.from({ length: Math.min(d.capacity, 8) }, (_, i) =>
    i < d.goingInitials.length ? 'other' : i === d.goingInitials.length && going ? 'me' : 'free',
  );
  const others = d.goingInitials.length;
  const started = new Date(d.startsAt).getTime() <= Date.now();

  return (
    <Screen>
      <Hero
        nav={back}
        right={<DemoBadge />}
        caption={`${cap(dayWord(d.startsAt))} · ${time(d.startsAt)}–${time(d.endsAt)}`}
        captionDot
        strip={<Strip items={[d.org.name, d.org.verified ? 'проверено' : null]} />}
      >
        <HeroTitle
          text={clean(d.title)}
          sticker={
            <Sticker>
              +{hoursStr(d.hours)}
              <br />ч
            </Sticker>
          }
        />
      </Hero>

      <div className="body">
        <Section title="Что делать" gap={8}>
          <div className="text">{d.description}</div>
          <div className="meta">
            {[d.address, d.addressNote, d.travelMin == null ? travelLabel(null, from ?? 'campus') : `≈${d.travelMin} мин${from === 'home' ? '' : ' от вуза'}`].filter(Boolean).join(' · ')}
          </div>
        </Section>

        <Section title="Кто идёт" aside={`${going ? `ты и ещё ${others}` : `${others} человек`} · свободно ${free}`}>
          {d.quorum && <div className="meta">Смена состоится, если к началу займут все {d.capacity} мест. Если команда не соберётся, запись отменится без неявки — бот сообщит об этом.</div>}
          <div className="avatars" role="img" aria-label={`Занято ${d.taken} из ${d.capacity} мест`}>
            {seats.map((s, i) => (
              <Avatar key={i} variant={s === 'free' ? 'empty' : 'seat'} initial={s === 'me' ? 'Я' : ''} />
            ))}
          </div>
          <LinkButton
            start
            className={invited ? 'btn-link--ok' : undefined}
            style={{ margin: '-8px 0 -8px -8px', padding: '0 8px' }}
            disabled={invite.isPending}
            onClick={() => invite.mutate()}
          >
            {invited ?? '+ Позвать друга'}
          </LinkButton>
          {invite.isError && <div className="error-text">{errorText(invite.error, 'Не получилось создать ссылку. Попробуй ещё раз.')}</div>}
        </Section>
        {going && (
          <Section title="На связи в MAX" gap={8}>
            <div className="meta">Бот пришлёт инструкцию и напоминание. Если есть вопрос о встрече или ты опаздываешь, напиши координатору — ответ придёт в этот же чат.</div>
            <LinkButton start onClick={() => openMaxLink(botChatLink(`contact_${going.id}`))}>
              Написать координатору в MAX
            </LinkButton>
          </Section>
        )}
      </div>

      <div className="spacer" />
      <Footer>
        <div className="meta center">{going ? `${instructionLine(d.instructionsAt, true)}. ${cancelLine(d.cancelUntil)}` : cancelLine(d.cancelUntil)}</div>
        {!going && free > 0 && <div className="meta center">{instructionLine(d.instructionsAt, false)}</div>}
        <SlideToConfirm
          label="Сдвинь — иду"
          doneLabel="Ты идёшь"
          done={Boolean(going)}
          busy={book.isPending}
          disabled={!going && (started || free <= 0)}
          disabledLabel={started ? 'Дело уже началось' : 'Мест нет'}
          onConfirm={() => book.mutate({ dealId: d.id, inviteToken })}
        />
        {book.isError && <div className="error-text center">{errorText(book.error, 'Не получилось записаться. Попробуй ещё раз.')}</div>}
        {cancel.isError && <div className="error-text center">{errorText(cancel.error, 'Не получилось отменить. Попробуй ещё раз.')}</div>}
        {calendar.isError && <div className="error-text center">Не получилось открыть календарь. Попробуй ещё раз.</div>}
        {going && (
          <div className="pair">
            <LinkButton disabled={calendar.isPending} onClick={() => calendar.mutate()}>
              {calendar.data === 'max' ? 'Файл открыт в MAX' : calendar.isSuccess ? 'Открыл файл календаря' : 'В календарь'}
            </LinkButton>
            <LinkButton tone="danger" disabled={cancel.isPending} onClick={() => cancel.mutate(going)}>
              Отменить запись
            </LinkButton>
          </div>
        )}
        {going && dayWord(d.startsAt) === 'сегодня' && (
          <LinkButton onClick={() => navigate(`/deals/${d.id}/check-in${from ? '?f=home' : ''}`)}>Я на месте — отметиться</LinkButton>
        )}
        {going && going.status === 'going' && new Date(d.startsAt) > new Date() && (
          <>
            <LinkButton disabled={transfer.isPending} className={transferCopied ? 'btn-link--ok' : undefined} onClick={() => transfer.mutate(going.id)}>
              {transferCopied ? 'Ссылка для друга готова' : 'Не смогу — передать место другу'}
            </LinkButton>
            {transferCopied && <div className="meta center" style={{ overflowWrap: 'anywhere' }}>{transferCopied}</div>}
            {transfer.isError && <div className="error-text center">{errorText(transfer.error, 'Не получилось создать ссылку. Попробуй ещё раз.')}</div>}
          </>
        )}
      </Footer>
    </Screen>
  );
}
