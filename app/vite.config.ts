import path from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  if (command === 'build' && mode === 'production' && env.VITE_USE_MOCKS === 'true' && env.VITE_ALLOW_MOCK_BUILD !== 'true') {
    throw new Error(
      'Production-сборка с VITE_USE_MOCKS=true. Для стенда: VITE_USE_MOCKS=false pnpm build; ' +
        'для демо-сборки на моках: VITE_ALLOW_MOCK_BUILD=true pnpm build.',
    );
  }
  return {
    base: './',
    plugins: [react()],
    resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
    server: { proxy: Object.fromEntries(['/api', '/files', '/check'].map((route) => [route, { target: env.VITE_PROXY_TARGET || 'http://localhost:8000', changeOrigin: true }])) },
  };
});
