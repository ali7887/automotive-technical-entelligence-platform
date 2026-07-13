# Production image for the ATIP web app (Next.js standalone output).
# Build from the REPO ROOT (pnpm workspace needs the root lockfile):
#   docker build -f apps/web/Dockerfile \
#     --build-arg NEXT_PUBLIC_API_URL=https://atip.example.com -t atip-web .
# NEXT_PUBLIC_API_URL is baked into the browser bundle at BUILD time —
# changing it requires rebuilding this image, not restarting it.

FROM node:22-alpine AS build
# corepack picks the pnpm version pinned in the root package.json
RUN corepack enable
WORKDIR /repo
# dependency layer first so source edits don't re-run pnpm install
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile --filter web
COPY apps/web apps/web
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_OUTPUT_STANDALONE=1 \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter web build

FROM node:22-alpine
RUN addgroup --system atip && adduser --system --ingroup atip atip
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1
# standalone output keeps the monorepo layout: server.js sits under apps/web/
COPY --from=build --chown=atip:atip /repo/apps/web/.next/standalone ./
COPY --from=build --chown=atip:atip /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=atip:atip /repo/apps/web/public ./apps/web/public
USER atip
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "apps/web/server.js"]
