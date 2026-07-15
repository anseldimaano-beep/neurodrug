FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json ./
RUN npm install

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_API_URL → baked into the browser-side bundle (user-facing URL)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# INTERNAL_API_URL → used only by the Next.js server proxy (Docker service name)
ARG INTERNAL_API_URL=http://api:8000
ENV INTERNAL_API_URL=$INTERNAL_API_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S neurodrug && adduser -S neurodrug -G neurodrug
COPY --from=builder /app/public ./public
COPY --from=builder --chown=neurodrug:neurodrug /app/.next/standalone ./
COPY --from=builder --chown=neurodrug:neurodrug /app/.next/static ./.next/static
USER neurodrug
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
