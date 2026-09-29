import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useGoBack } from '@/lib/nav';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import { UniversityNotice } from '@/ui/UniversityNotice';
import { Chips, DemoBadge, ErrorState, Footer, Hero, HeroTitle, Loading, PrimaryButton, Screen, Section, Strip } from '@/ui';

export function PlaceScreen() {
  const navigate = useNavigate();
  const goBack = useGoBack();
  const qc = useQueryClient();
  const [sp] = useSearchParams();
  const next = sp.get('next');
  const dict = useQuery({ queryKey: ['dictionaries'], queryFn: api.dictionaries, staleTime: Infinity });
  const [uni, setUni] = useState<string | null>(null);
  const [district, setDistrict] = useState<string | null>(null);

  const onboard = useMutation({
    mutationFn: () => api.onboard({ universityId: uni!, districtId: district! }),
    onSuccess: (me) => {
      qc.setQueryData(['me'], me);
      navigate(next ?? '/', { replace: true });
    },
  });

  const back = { label: '‹ Назад', onClick: goBack };
  const uniName = dict.data?.universities.find((u) => u.id === uni)?.name;
  const districtName = dict.data?.districts.find((d) => d.id === district)?.name;
  const ok = Boolean(uni && district);
  const strip = uniName || districtName ? `${uniName ?? 'вуз?'} → ${districtName ?? 'район?'}` : 'Вуз → район';
  const hint = ok ? '' : !uni && !district ? 'Выбери вуз и район' : !uni ? 'Осталось выбрать вуз' : 'Осталось выбрать район';

  return (
    <Screen>
      <Hero
        nav={back}
        right={<DemoBadge />}
        caption="Спрошу один раз"
        strip={
          <Strip>
            <span style={{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{strip}</span>
          </Strip>
        }
      >
        <HeroTitle text="Откуда считать дорогу" />
      </Hero>

      {dict.isPending ? (
        <Loading />
      ) : dict.isError ? (
        <ErrorState error={dict.error} onRetry={() => dict.refetch()} />
      ) : (
        <div className="body body--tight">
          <div className="text">Дорогу считаю от корпуса вуза. По району подбираю дела ближе к дому, когда окно в выходной или вечером.</div>
          <Section title="Где учишься" gap={8}>
            <Chips<string>
              label="Где учишься"
              allowNone
              options={dict.data.universities.map((u) => ({ value: u.id, label: u.name }))}
              value={uni}
              onChange={setUni}
            />
            <UniversityNotice universityId={uni} />
          </Section>
          <Section title="Район, где живёшь" gap={8}>
            <Chips<string>
              label="Район, где живёшь"
              allowNone
              options={dict.data.districts.map((d) => ({ value: d.id, label: d.name }))}
              value={district}
              onChange={setDistrict}
            />
          </Section>
          <div className="meta">Можно поменять в профиле в любой момент.</div>
        </div>
      )}

      <div className="spacer" />
      <Footer>
        {hint && <div className="meta center">{hint}</div>}
        {onboard.isError && <div className="error-text center">{errorText(onboard.error, 'Не получилось сохранить. Попробуй ещё раз.')}</div>}
        <PrimaryButton disabled={!ok || onboard.isPending} onClick={() => onboard.mutate()}>
          Показать дела
        </PrimaryButton>
      </Footer>
    </Screen>
  );
}
