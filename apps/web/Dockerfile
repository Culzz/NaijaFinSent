# --- Stage 1: build the static bundle ---------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Install deps first so Docker layer caching survives source-only changes.
COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .

# API base URL is baked in at build time; override with --build-arg.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_USE_MOCKS=false
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_USE_MOCKS=$VITE_USE_MOCKS

RUN npm run build

# --- Stage 2: serve with nginx ----------------------------------------------
FROM nginx:1.27-alpine AS runtime

RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/naijafinsent.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
