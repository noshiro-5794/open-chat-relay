/// <reference types="vite/client" />

declare global {
  interface Window {
    __OPEN_CHAT_RELAY_DEMO_CONFIG__?: {
      apiBaseUrl?: string;
    };
    openChatRelayDesktop?: {
      platform: string;
      version: string;
    };
  }
}

export {};
