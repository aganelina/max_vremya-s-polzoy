import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

export const canGoBack = () => ((window.history.state as { idx?: number } | null)?.idx ?? 0) > 0;

export function useGoBack() {
  const navigate = useNavigate();
  return useCallback(() => {
    if (canGoBack()) navigate(-1);
    else navigate('/', { replace: true });
  }, [navigate]);
}
