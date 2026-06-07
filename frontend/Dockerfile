FROM oven/bun:1.2-slim

WORKDIR /app

COPY package.json bun.lock bunfig.toml ./
RUN bun install --frozen-lockfile

COPY . .

EXPOSE 5173
# VITE_* vars are injected at runtime via docker-compose env_file (.env)
CMD ["bun", "run", "dev", "--host", "0.0.0.0", "--port", "5173"]
