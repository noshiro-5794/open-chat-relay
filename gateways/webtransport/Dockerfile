FROM node:25-trixie-slim

WORKDIR /app

COPY gateways/webtransport/package.json gateways/webtransport/package-lock.json ./
RUN npm ci --omit=dev

COPY gateways/webtransport/src ./src
COPY gateways/webtransport/scripts ./scripts

ENV NODE_ENV=production
ENV OPEN_CHAT_RELAY_GATEWAY_BIND_HOST=0.0.0.0
ENV OPEN_CHAT_RELAY_GATEWAY_PORT=8080

EXPOSE 8080

CMD ["node", "src/server.js"]
