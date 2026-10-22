"""Ajustes del panel, en un fichero local (data/settings.json, fuera de git).

Solo los lee el panel (y el bot, para sus avisos): el pipeline, evaluate.py y fill_test.py no importan este módulo
y usan siempre la configuración evaluada. Cambiar un ajuste nunca altera la entrega ni los resultados guardados
(tests/test_settings.py lo comprueba).
"""
from __future__ import annotations

import json

from .config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"

# valor por defecto de cada ajuste: el tipo del valor decide cómo se valida
DEFAULTS: dict = {
    "source": "default",         # "default" (noticias del test) o "custom" (noticias cargadas)
    "live_ai": True,             # modo demo: IA en directo (sin la caché del LLM)
    "ai_timeout_s": 60,          # tiempo máximo de la IA en directo; después, el resultado precalculado
    "margin_tight_days": 14,     # margen por debajo del cual hay peligro (calendario y colores del margen)
    "urgent_buy_days": 7,        # plazo de una compra urgente sin alternativo libre (calendario)
    "recurrent_min": 3,          # pedidos en 6 meses para ser proveedor habitual
    "urgent_mode": "inmediato",  # avisos de alertas urgentes: "inmediato" o "resumen"
}
LIMITS = {"ai_timeout_s": (10, 600), "margin_tight_days": (1, 60), "urgent_buy_days": (1, 60),
          "recurrent_min": (1, 6)}
URGENT_MODES = ("inmediato", "resumen")


def _clean(key: str, value):
    """El valor validado, o el de por defecto si no es válido (un fichero editado a mano no rompe el panel)."""
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        lo, hi = LIMITS[key]
        return min(max(int(value), lo), hi)
    if key == "urgent_mode":
        return value if value in URGENT_MODES else default
    if key == "source":
        return value if value in ("default", "custom") else default
    return default


def load() -> dict:
    """Todos los ajustes (los que falten, con su valor por defecto)."""
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    return {k: _clean(k, raw.get(k, v)) for k, v in DEFAULTS.items()}


def get(key: str):
    return load()[key]


def save(**values) -> dict:
    """Guarda los ajustes indicados (validados) y devuelve todos."""
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise KeyError(f"ajuste desconocido: {', '.join(sorted(unknown))}")
    current = load()
    current.update({k: _clean(k, v) for k, v in values.items()})
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")
    return current


def reset(keep: tuple[str, ...] = ("source",)) -> dict:
    """Vuelve a los valores por defecto (menos los de `keep`: la fuente de noticias tiene su propio botón)."""
    current = load()
    return save(**{k: v for k, v in DEFAULTS.items() if k not in keep}, **{k: current[k] for k in keep})
