FROM node:25-alpine AS build

WORKDIR /app

COPY apps/console/package.json apps/console/package-lock.json ./
RUN npm ci

COPY apps/console/index.html apps/console/tsconfig.json apps/console/vite.config.ts ./
COPY apps/console/public ./public
COPY apps/console/src ./src
RUN npm run build

FROM node:25-alpine

WORKDIR /app

ENV NODE_ENV=production
ENV OPEN_CHAT_RELAY_CONSOLE_BIND_HOST=0.0.0.0
ENV OPEN_CHAT_RELAY_CONSOLE_PORT=8080

COPY apps/console/server.mjs ./server.mjs
COPY --from=build /app/dist ./dist

EXPOSE 8080

CMD ["node", "server.mjs"]
