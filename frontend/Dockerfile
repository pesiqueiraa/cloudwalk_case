# Telas em React: build do Vite servido pelo "vite preview" na porta 5173
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# O navegador chama a plataforma pela porta publicada no host
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build
EXPOSE 5173
CMD ["npx", "vite", "preview"]
