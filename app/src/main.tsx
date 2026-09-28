import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MaxUI } from '@maxhub/max-ui';
import '@maxhub/max-ui/styles.css';
import './styles/fonts.css';
import './styles/app.css';
import { readStartRoute } from './lib/start';
import { App } from './App';
import { getPlatform, loadMaxBridge, notifyReady } from './max/bridge';
import { initApi } from './api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

void Promise.all([loadMaxBridge(), initApi()]).then(() => {
  const startRoute = readStartRoute();
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <MaxUI platform={getPlatform() ?? 'ios'} colorScheme="light">
        <QueryClientProvider client={queryClient}>
          <App startRoute={startRoute} />
        </QueryClientProvider>
      </MaxUI>
    </StrictMode>,
  );
  notifyReady();
});
