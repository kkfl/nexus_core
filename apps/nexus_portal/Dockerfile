FROM node:20-slim AS builder

WORKDIR /app
COPY apps/nexus_portal/package*.json ./
RUN npm install

COPY apps/nexus_portal/ .
# We need to pass VITE_API_BASE_URL during build
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

ARG VITE_APP_NAME="Nexus Portal"
ENV VITE_APP_NAME=$VITE_APP_NAME

RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY apps/nexus_portal/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
