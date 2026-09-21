FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY . .
ARG MAX_BOT_USERNAME=""
ARG SEED_DEMO="false"
ENV VITE_USE_MOCKS=false \
    VITE_DEMO_ENABLED=${SEED_DEMO} \
    VITE_API_BASE=/api/v1 \
    VITE_MAX_BRIDGE_URL=https://st.max.ru/js/max-web-app.js \
    VITE_BOT_USERNAME=${MAX_BOT_USERNAME}
RUN pnpm build

FROM caddy:2
COPY --from=build /app/dist /srv
