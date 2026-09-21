/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCKS?: string;
  readonly VITE_DEMO_ENABLED?: string;
  readonly VITE_ALLOW_MOCK_BUILD?: string;
  readonly VITE_API_BASE?: string;
  readonly VITE_MAX_BRIDGE_URL?: string;
  readonly VITE_DEV_USER?: string;
  readonly VITE_BOT_USERNAME?: string;
}
