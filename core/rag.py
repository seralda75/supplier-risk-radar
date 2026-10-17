"""Búsqueda de ejemplos parecidos en ChromaDB persistente (embeddings de Ollama).

Adaptado del kit: en lugar de trocear ficheros, indexa registros (las noticias de
entrenamiento con su etiqueta y su Explanation) para usarlos como few-shot.
Ojo: Chroma exige nombres de colección de al menos 3 caracteres.
"""
from __future__ import annotations

from . import llm
from .config import CHROMA_DIR


def _collection(name: str):
    import chromadb
    if len(name) < 3:
        raise ValueError("Chroma exige nombres de colección de al menos 3 caracteres")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})


def reset(name: str) -> None:
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if name in [c.name for c in client.list_collections()]:
        client.delete_collection(name)


def index_records(records: list[dict], name: str, text_key: str = "text", id_key: str = "id") -> int:
    """Indexa registros {id, text, ...metadatos}. Los metadatos deben ser str/int/float/bool."""
    if not records:
        return 0
    col = _collection(name)
    texts = [r[text_key] for r in records]
    col.upsert(
        ids=[str(r[id_key]) for r in records],
        documents=texts,
        embeddings=llm.embed(texts),
        metadatas=[{k: v for k, v in r.items() if k not in (text_key, id_key)} for r in records],
    )
    return len(records)


def count(name: str) -> int:
    return _collection(name).count()


def search(query: str, name: str, k: int = 4, exclude_ids: set[str] | None = None) -> list[dict]:
    """Devuelve los k registros más parecidos. `exclude_ids` permite hacer leave-one-out."""
    col = _collection(name)
    n = col.count()
    if n == 0:
        return []
    exclude_ids = exclude_ids or set()
    res = col.query(query_embeddings=llm.embed([query]), n_results=min(k + len(exclude_ids), n))
    hits = [
        {"id": i, "text": d, "score": round(1 - dist, 3), **m}
        for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
        if i not in exclude_ids
    ]
    return hits[:k]
