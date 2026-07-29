# Fumadocs docs app: bun build -> Next standalone -> node runtime.
FROM oven/bun:1 AS build
WORKDIR /app
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile || bun install
COPY . .
# content/docs is generated MDX (by ckdocs); it must be present in the build context.
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_WORKER_URL=http://localhost:8000
ENV NEXT_PUBLIC_WORKER_URL=${NEXT_PUBLIC_WORKER_URL}
RUN bun run build

FROM node:22-slim AS run
WORKDIR /app
ENV NODE_ENV=production PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
