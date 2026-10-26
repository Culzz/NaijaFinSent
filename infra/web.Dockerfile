FROM node:20-slim AS build

WORKDIR /app/web

# Vite envs are baked at build time, so the API location is a build arg.
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ARG VITE_USE_MOCKS=false
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_USE_MOCKS=$VITE_USE_MOCKS

COPY apps/web/package*.json ./
RUN npm ci || npm install --no-audit --no-fund

COPY apps/web ./
RUN npm run build

FROM node:20-slim
WORKDIR /app/web
COPY --from=build /app/web/dist ./dist
RUN npm install -g serve
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
