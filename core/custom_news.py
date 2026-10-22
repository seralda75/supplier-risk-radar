"""Noticias cargadas por el usuario (xlsx o csv) como fuente del panel, en lugar de las del test.

    read(bytes, nombre)  ->  noticias validadas (o NewsFileError con el motivo, en español)
    process(noticias)    ->  las pasa por el pipeline (con su caché) y guarda data/custom/news_results.json
    info() / clear()     ->  qué hay cargado / volver a la fuente por defecto

Todo va a data/custom/: nunca toca data/results (los resultados de la entrega), outputs/ ni deliverables/. El
pipeline se llama con log=False, así que tampoco escribe en la auditoría. Qué fuente usa el panel lo decide
core/settings.py ("source").
"""
from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from . import results, settings

REQUIRED = ["News_ID", "Published_Date", "Source", "Headline", "Summary"]
MAX_NEWS = 200
INPUT_NAME = "news_input.json"


class NewsFileError(ValueError):
    """El fichero no se puede usar: el mensaje dice por qué."""


def input_path() -> Path:
    return results.path(results.CUSTOM).with_name(INPUT_NAME)


def _frame(data: bytes, filename: str) -> pd.DataFrame:
    """La tabla con las columnas obligatorias: en un xlsx, la primera hoja que las tenga."""
    ext = Path(filename).suffix.lower()
    if ext == ".csv":
        for enc in ("utf-8-sig", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(data), sep=None, engine="python", encoding=enc, dtype=str)
            except UnicodeDecodeError:
                continue
            except Exception as e:                               # noqa: BLE001
                raise NewsFileError(f"No se pudo leer el CSV: {e}") from e
        raise NewsFileError("No se pudo leer el CSV (codificación desconocida).")
    if ext not in (".xlsx", ".xlsm"):
        raise NewsFileError("Formato no admitido: usa un fichero .xlsx o .csv.")
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str)
    except Exception as e:                                       # noqa: BLE001
        raise NewsFileError(f"No se pudo leer el Excel: {e}") from e
    for df in sheets.values():
        if set(REQUIRED) <= {str(c).strip() for c in df.columns}:
            return df
    return next(iter(sheets.values()), pd.DataFrame())


def read(data: bytes, filename: str) -> list[dict]:
    """Noticias validadas: columnas obligatorias, ID y titular no vacíos, IDs únicos y fecha válida."""
    df = _frame(data, filename)
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise NewsFileError("Faltan columnas: " + ", ".join(missing) + ". Se necesitan: " + ", ".join(REQUIRED) + ".")
    df = df.dropna(how="all")
    if df.empty:
        raise NewsFileError("El fichero no tiene noticias.")
    if len(df) > MAX_NEWS:
        raise NewsFileError(f"Demasiadas noticias ({len(df)}): el máximo es {MAX_NEWS}.")
    out, seen = [], set()
    for i, r in enumerate(df.to_dict("records"), start=2):          # fila 2 = la primera de datos
        nid = str(r["News_ID"]).strip() if pd.notna(r["News_ID"]) else ""
        head = str(r["Headline"]).strip() if pd.notna(r["Headline"]) else ""
        if not nid or not head:
            raise NewsFileError(f"Fila {i}: News_ID y Headline no pueden estar vacíos.")
        if nid in seen:
            raise NewsFileError(f"Fila {i}: el News_ID «{nid}» está repetido.")
        seen.add(nid)
        try:
            date = pd.to_datetime(r["Published_Date"]).date().isoformat()
        except (ValueError, TypeError):
            raise NewsFileError(f"Fila {i}: Published_Date no es una fecha válida.") from None
        out.append({"News_ID": nid, "Published_Date": date,
                    "Source": str(r["Source"]).strip() if pd.notna(r["Source"]) else "",
                    "Headline": head, "Summary": str(r["Summary"]).strip() if pd.notna(r["Summary"]) else ""})
    return out


def process(news: list[dict], name: str = "", progress: Callable[[int, int, str], None] | None = None,
            use_llm: bool | None = None) -> dict:
    """Pasa las noticias por el pipeline (con la caché del LLM si ya se procesaron) y las guarda como fuente.
    use_llm=None: con IA si Ollama responde, solo con reglas si no. progress(hecho, total, titular)."""
    from .config import LLM_MODEL
    from .pipeline import assess
    if use_llm is None:
        from . import llm
        use_llm = llm.is_up()
    out = []
    for i, n in enumerate(news):
        if progress:
            progress(i, len(news), n["Headline"])
        r = assess(n, use_llm=use_llm, log=False, model=LLM_MODEL).model_dump()
        r["summary"] = n.get("Summary", "")
        out.append(r)
    results.save(results.CUSTOM, out, "llm" if use_llm else "reglas", LLM_MODEL if use_llm else "",
                 source_name=name, news=len(out))
    input_path().write_text(json.dumps({"name": name, "news": news}, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress(len(news), len(news), "")
    return info() or {}


def info() -> dict | None:
    """{name, loaded_at, news, mode} de las noticias cargadas, o None si no hay."""
    d = results.load(results.CUSTOM)
    if not d:
        return None
    return {"name": d.get("source_name", ""), "loaded_at": d["generated"], "news": len(d["results"]),
            "mode": d["mode"]}


def stored_input() -> tuple[str, list[dict]] | None:
    """Las noticias del último fichero cargado (para reprocesarlas), o None."""
    try:
        d = json.loads(input_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d["name"], d["news"]


def active() -> bool:
    """¿El panel usa las noticias cargadas? (ajuste «source» y fichero presente)"""
    return settings.get("source") == "custom" and results.path(results.CUSTOM).exists()


def use(on: bool) -> None:
    settings.save(source="custom" if on else "default")


def clear() -> None:
    """Vuelve a las noticias del día y borra las cargadas (solo data/custom)."""
    use(False)
    for p in (results.path(results.CUSTOM), input_path()):
        p.unlink(missing_ok=True)
