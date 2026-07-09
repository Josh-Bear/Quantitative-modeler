# Build context = black_litterman_model/ (see docker-compose.yml) so the
# canonical engine/ and style.css can be copied in — the copies under
# frontend/public/engine and frontend/src/style.css are generated, not tracked.
FROM node:20-alpine
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY engine/ ./public/engine/
COPY style.css ./src/style.css
EXPOSE 5173
# Plain `vite` (not `npm run dev`) — the predev sync script needs ../engine,
# which doesn't exist inside the container; the COPYs above already did it.
CMD ["npx", "vite", "--host", "0.0.0.0"]
