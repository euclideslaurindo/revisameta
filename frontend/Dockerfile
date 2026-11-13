# Builds the Angular app and serves it with Caddy (multi-arch base images).
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx ng build --configuration production

FROM caddy:2.11.9-alpine
COPY --from=build /app/dist/frontend/browser /srv
