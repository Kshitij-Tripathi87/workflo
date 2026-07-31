# Cortex Autopilot frontend - Next.js standalone output
FROM node:20-alpine AS builder

WORKDIR /app

# Build args for NEXT_PUBLIC_ vars (server-time broadcast)
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

COPY package.json package-lock.json* ./
# `npm ci` is non-fallback; linting/CI must rely on a separate lockfile check.
# We need devDependencies (typescript, types) for `next build` compilation.
RUN npm ci --include=dev

COPY . .
RUN npm run build

# --- Runtime stage ---
FROM node:20-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Copy standalone build
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
