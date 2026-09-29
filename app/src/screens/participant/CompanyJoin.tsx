import { useEffect, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import { useRefreshDeals } from '@/lib/useBooking';
import { DemoBadge, ErrorState, Hero, Loading, Screen } from '@/ui';

export function CompanyJoinScreen() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const refresh = useRefreshDeals();
  const join = useMutation({
    mutationFn: () => api.joinCompany(token),
    onSuccess: (c) => {
      qc.setQueryData(['company', c.id], c);
      void refresh();
      navigate(`/company/${c.id}`, { replace: true });
    },
  });
  const { mutate } = join;
  const joined = useRef<string | null>(null);
  useEffect(() => {
    if (joined.current === token) return;
    joined.current = token;
    mutate();
  }, [mutate, token]);

  return (
    <Screen>
      <Hero striped right={<DemoBadge />} caption="Компания" />
      {join.isError ? (
        <ErrorState text={errorText(join.error, 'Не получилось вступить в компанию. Попробуй ещё раз.')} onRetry={() => join.mutate()} />
      ) : (
        <Loading />
      )}
    </Screen>
  );
}
