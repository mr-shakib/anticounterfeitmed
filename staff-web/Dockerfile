# syntax=docker/dockerfile:1
FROM node:24-alpine AS build
WORKDIR /app
COPY staff-web/package*.json ./
RUN npm ci
COPY staff-web/ ./
# The mount point is baked in at build time: Next.js needs it for routing, and
# the API client needs it to prefix its requests.
ARG PORTAL_BASE_PATH=/staff
ENV PORTAL_BASE_PATH=${PORTAL_BASE_PATH}
ENV NEXT_PUBLIC_BASE_PATH=${PORTAL_BASE_PATH}
# Next.js writes rewrite destinations into routes-manifest.json at build time,
# so this has to be known here and not only at runtime. Left unset, the build
# freezes in the development default and the deployed portal proxies to its own
# loopback, which fails with ECONNREFUSED and reads as a 500 on sign-in.
ARG BACKEND_ORIGIN=http://api:8000
ENV BACKEND_ORIGIN=${BACKEND_ORIGIN}
RUN npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production
# The mount point is needed at runtime as well as at build time. next.config.ts
# reads it on start, and if it is missing there the server routes at the origin
# root while the built assets expect the prefix -- every page but the index 404s.
ARG PORTAL_BASE_PATH=/staff
ENV PORTAL_BASE_PATH=${PORTAL_BASE_PATH}
ENV NEXT_PUBLIC_BASE_PATH=${PORTAL_BASE_PATH}
COPY --from=build /app/package*.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.ts ./
RUN addgroup -g 10003 portal && adduser -u 10003 -G portal -D portal && chown -R portal /app
USER portal
EXPOSE 3000
CMD ["npm", "run", "start", "--", "-p", "3000"]
