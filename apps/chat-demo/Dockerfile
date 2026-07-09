FROM node:25-alpine AS build

WORKDIR /app

COPY apps/chat-demo/package.json apps/chat-demo/package-lock.json ./
RUN npm ci

COPY packages/sdk-js ../../packages/sdk-js
COPY apps/chat-demo/index.html apps/chat-demo/tsconfig.json apps/chat-demo/vite.config.ts ./
COPY apps/chat-demo/public ./public
COPY apps/chat-demo/src ./src
RUN npm run build:web

FROM node:25-alpine

WORKDIR /app

ENV NODE_ENV=production
ENV OPEN_CHAT_RELAY_DEMO_BIND_HOST=0.0.0.0
ENV OPEN_CHAT_RELAY_DEMO_PORT=8080

COPY apps/chat-demo/server.mjs ./server.mjs
COPY --from=build /app/dist ./dist

EXPOSE 8080

CMD ["node", "server.mjs"]
