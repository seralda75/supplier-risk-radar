"""Cliente mínimo de Ollama (sin dependencias raras: solo requests).

- chat():        texto libre
- extract():     salida estructurada validada con un modelo Pydantic (usa JSON schema nativo de Ollama)
- embed():       embeddings para RAG

Las respuestas de extract() se cachean en disco por hash (modelo + prompt + esquema):
si solo cambian las reglas de urgencia, re-evaluar no vuelve a llamar al LLM.
"""
from __future__ import annotations

import hashlib
import json
import warnings
from typing import Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .config import EMBED_MODEL, LLM_CACHE_DIR, LLM_MODEL, NUM_CTX, OLLAMA_URL, USE_LLM_CACHE

T = TypeVar("T", bound=BaseModel)
TIMEOUT = 300


def is_up() -> bool:
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).ok
    except requests.RequestException:
        return False


def installed_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def chat(prompt: str, system: str = "", model: str = LLM_MODEL, temperature: float = 0.2) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": False,
              "options": {"temperature": temperature, "num_ctx": NUM_CTX}},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _cache_key(model: str, system: str, prompt: str, schema: dict) -> str:
    blob = json.dumps([model, system, prompt, schema], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def extract(text: str, schema: Type[T], instructions: str = "", model: str = LLM_MODEL,
            retries: int = 2, system: str | None = None, use_cache: bool = USE_LLM_CACHE) -> T:
    """Extrae datos estructurados del texto y los valida con Pydantic. Reintenta si falla.

    `system` sustituye al prompt de sistema genérico (el juez de noticias trae el suyo).
    """
    if system is None:
        system = (
            "Eres un sistema de extracción de datos. Devuelve SOLO JSON válido que cumpla el esquema. "
            "Si un dato no aparece, usa null. No inventes valores. "
            "Incluye un campo 'confidence' entre 0 y 1 con tu seguridad global."
            + (f"\n{instructions}" if instructions else "")
        )
    json_schema = schema.model_json_schema()
    cache_file = LLM_CACHE_DIR / f"{_cache_key(model, system, text, json_schema)}.json"
    if use_cache and cache_file.exists():
        try:
            return schema.model_validate_json(cache_file.read_text(encoding="utf-8"))
        except ValidationError:
            cache_file.unlink()  # el esquema cambió: se ignora la caché antigua

    last_err = ""
    for _ in range(retries + 1):
        prompt = text + (f"\n\nEl intento anterior falló: {last_err}" if last_err else "")
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": model, "stream": False, "format": json_schema,
                  "options": {"temperature": 0, "num_ctx": NUM_CTX},
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}]},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("prompt_eval_count", 0) >= NUM_CTX - 64:
            warnings.warn(f"El prompt ({body['prompt_eval_count']} tokens) roza NUM_CTX={NUM_CTX}: "
                          "Ollama puede haberlo truncado. Sube NUM_CTX o acorta el prompt.")
        raw = body["message"]["content"]
        try:
            result = schema.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = str(e)[:500]
            continue
        if use_cache:
            cache_file.write_text(result.model_dump_json(), encoding="utf-8")
        return result
    raise ValueError(f"No se pudo extraer un JSON válido: {last_err}")


def embed(texts: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
    r = requests.post(f"{OLLAMA_URL}/api/embed", json={"model": model, "input": texts}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["embeddings"]
