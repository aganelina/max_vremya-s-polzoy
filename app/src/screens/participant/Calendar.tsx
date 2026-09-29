import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '@/api';
import { useGoBack } from '@/lib/nav';
import { dayMonth, time, ymd } from '@/lib/format';
import { PILOT_DAYS, PILOT_WEEKS } from '@/lib/pilot';
import { Chips, ErrorState, Hero, HeroTitle, Loading, Screen, Ticket } from '@/ui';

export function CalendarScreen() {
  const navigate = useNavigate();
  const back = useGoBack();
  const [params, setParams] = useSearchParams();
  const days = Array.from({ length: PILOT_DAYS + 1 }, (_, i) => ymd(new Date(), i));
  const requested = params.get('date');
  const date = requested && days.includes(requested) ? requested : days[0];
  const week = Math.floor((days.indexOf(date) - 1) / 7);
  const setDate = (date: string) => setParams({ date }, { replace: true });
  const q = useQuery({ queryKey: ['events', date], queryFn: () => api.events(date) });
  return <Screen>
    <Hero nav={{ label: '‹ Назад', onClick: back }} caption="Планируй заранее">
      <HeroTitle text={`Афиша на ${PILOT_WEEKS} недель`} />
    </Hero>
    <div className="body body--tight">
      <Chips label="Неделя" options={[
        { value: '-1', label: 'Сегодня' },
        ...Array.from({ length: PILOT_WEEKS }, (_, value) => ({ value: String(value), label: `${value + 1}-я неделя` })),
      ]} value={String(week)} onChange={(v) => v !== null && setDate(days[Number(v) < 0 ? 0 : Number(v) * 7 + 1])} />
      {week >= 0 && <Chips label="День события" options={days.slice(week * 7 + 1, week * 7 + 8).map((value) => ({ value, label: dayMonth(value + 'T12:00:00') }))}
        value={date} onChange={(v) => v && setDate(v)} />}
      <div className="meta">Все события на выбранный день. В карточке — время, адрес и запись.</div>
      {q.isPending ? <Loading /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> :
        <div className="event-grid">
          {q.data.length === 0 && <div className="card card--dashed">На этот день пока нет событий. Выбери другую дату.</div>}
          {q.data.map((d) => <Ticket key={d.id} title={d.title} kicker={d.org.name} time={time(d.startsAt)}
            lines={[d.address, `${time(d.startsAt)}–${time(d.endsAt)}`]} stubLabel={d.myBooking ? 'ИДЁШЬ' : 'ОТКРЫТЬ'}
            onClick={() => navigate(`/deals/${d.id}`)} />)}
        </div>}
    </div>
  </Screen>;
}
