import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api';
import type { Booking } from '@/api/types';

export function useRefreshDeals() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ['deal'] }),
      qc.invalidateQueries({ queryKey: ['my-deals'] }),
      qc.invalidateQueries({ queryKey: ['search'] }),
      qc.invalidateQueries({ queryKey: ['search-preview'] }),
      qc.invalidateQueries({ queryKey: ['company'] }),
    ]);
}

export function useBooking() {
  const refresh = useRefreshDeals();
  const book = useMutation({
    mutationFn: ({ dealId, companyId, inviteToken }: { dealId: string; companyId?: string; inviteToken?: string }) => api.book(dealId, { companyId, inviteToken }),
    onSuccess: refresh,
  });
  const cancel = useMutation({
    mutationFn: (b: Booking) => api.cancelBooking(b.id),
    onSuccess: refresh,
  });
  return { book, cancel };
}
