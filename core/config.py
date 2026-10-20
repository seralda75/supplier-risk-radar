"""Configuración central. Cambia aquí los modelos y las rutas sin tocar el resto del código."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"               # Excel originales del reto
CHROMA_DIR = DATA_DIR / "chroma"
DB_PATH = DATA_DIR / "app.db"            # auditoría (SQLite)
LLM_CACHE_DIR = DATA_DIR / "llm_cache"   # respuestas del LLM cacheadas por hash del prompt
OUTPUT_DIR = ROOT / "outputs"


def _find_excel(pattern: str) -> Path:
    """Los Excel llegaron con nombres tipo 'Copia de Copy of ..._.xlsx': se buscan por patrón.
    Si hay copias duplicadas (la validación llegó dos veces), se usa la de nombre más corto."""
    found = sorted(RAW_DIR.glob(pattern), key=lambda p: (len(p.name), p.name))
    if not found:
        raise FileNotFoundError(f"No hay ningún Excel que cumpla '{pattern}' en {RAW_DIR}")
    return found[0]


TRAIN_XLSX = _find_excel("*Training*.xlsx")
VALIDATION_XLSX = _find_excel("*Validation*.xlsx")
TEST_XLSX = _find_excel("*Test*.xlsx")
TEST_OUTPUT_XLSX = OUTPUT_DIR / "Supplier_Risk_3_Test_respuestas.xlsx"

# 127.0.0.1 y no "localhost": en Windows, localhost prueba antes IPv6 (::1), donde Ollama no escucha,
# y cada llamada pierde ~2 s hasta caer a IPv4 (medido: 2,1 s frente a 0,08 s).
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")             # se fija tras medir en scripts/bench_models.py
LLM_FAST_MODEL = os.getenv("LLM_FAST_MODEL", "llama3.2:3b")  # por si el portátil va justo
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
# Contexto explícito: Ollama trunca el prompt en silencio si supera su valor por defecto
# (4096 basta: el prompt del juez ocupa ~600-1500 tokens; más contexto gasta VRAM de la GPU de 4 GB)
NUM_CTX = int(os.getenv("NUM_CTX", "4096"))
USE_LLM_CACHE = os.getenv("USE_LLM_CACHE", "1") == "1"

# Por debajo de este umbral, el caso va a revisión humana
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))

for d in (DATA_DIR, LLM_CACHE_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)
