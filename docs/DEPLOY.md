# Despliegue con Docker

Tres servicios: **ollama** (modelo local), **app** (panel Streamlit) y **bot** (Telegram, opcional).
App y bot comparten `./data` (SQLite, caché del LLM, Chroma), así que una decisión tomada en el móvil
aparece en el panel.

## Requisitos
- Docker Desktop (Windows/macOS) o Docker Engine + Compose v2 (Linux).
- ~8 GB de disco para los modelos. GPU NVIDIA opcional (ver `docker-compose.yml`).

## Primera vez
```bash
cp .env.example .env            # y pega el token: TELEGRAM_BOT_TOKEN=...
docker compose up -d ollama
docker compose --profile init run --rm init-models   # descarga qwen2.5:7b y nomic-embed-text
docker compose up -d --build app
```
Panel: http://localhost:8501 (modo demo: http://localhost:8501/?demo=1)

## Con el bot de Telegram
```bash
docker compose --profile bot up -d
```

## Operación
```bash
docker compose logs -f app                       # ver registros
docker compose exec app python scripts/reset_demo.py   # limpiar la demo
docker compose exec app python fill_test.py      # regenerar la entrega
docker compose down                              # parar (los datos de ./data se conservan)
```

## Notas
- Sin GPU, cada noticia con IA en directo tarda bastante más: usa la caché (`data/llm_cache`).
- El token nunca entra en la imagen: se lee de `.env` en tiempo de ejecución (`.dockerignore` lo excluye).
- En un servidor, pon el panel detrás de un proxy con HTTPS y autenticación: Streamlit no trae login.
- El enlace "Ver en el panel" del bot apunta a `localhost:8501`; en un servidor, cámbialo por la URL pública.
