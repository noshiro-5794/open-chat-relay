# OpenChatRelay Chat Demo

Shared React/TypeScript chat demo for OpenChatRelay.

The same UI runs as:

- a web demo through Vite or the static `server.mjs`
- a Windows desktop demo through Electron

The demo uses the TypeScript SDK for realtime transport negotiation and falls
back through WebTransport, WebSocket, and SSE according to `/v1/capabilities`.

## Web

```bash
npm install
npm run dev:web
```

Set the API base URL with:

```bash
VITE_OPEN_CHAT_RELAY_API_BASE_URL=https://api.chat.example.com npm run dev:web
```

You can also edit the Server field on the login screen. The value is saved in
browser storage and reused by the SDK connection.

For local browser testing against a production API, add the Vite origin to the
API CORS configuration:

```env
OPEN_CHAT_RELAY_CORS_ORIGINS=https://console.chat.example.com,https://app.chat.example.com,http://localhost:5174
```

For a production web build:

```bash
npm run build:web
OPEN_CHAT_RELAY_DEMO_PORT=8082 npm start
```

## Windows Desktop

Run the Vite renderer in one terminal:

```bash
npm run dev:web
```

Run Electron in another terminal:

```bash
ELECTRON_RENDERER_URL=http://localhost:5174 npm run dev:desktop
```

On Windows PowerShell:

```powershell
$env:ELECTRON_RENDERER_URL="http://localhost:5174"; npm run dev:desktop
```

Build a Windows installer:

```bash
npm run package:windows
```

The Windows build writes artifacts to `release/`. Building the final `.exe` is
best done on Windows or a Windows CI runner so the NSIS installer and signing
steps are verified in the same environment users run.

The packaged app includes `dist/config.js` and also lets users edit the Server
field on the login screen. For a production Windows demo, edit
`public/config.js` before packaging or keep the default and enter the API URL at
runtime.
