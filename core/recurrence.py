"""Recurrencia de compra: con qué proveedores trabaja de forma habitual cada comprador.

Los datos del reto no traen historial de compras: data/purchase_history.csv es SINTÉTICO, generado por
scripts/build_purchase_history.py con semilla fija (ver docs/fase6_telegram.md).
"""
from __future__ import annotations

from .config import DATA_DIR

HISTORY_PATH = DATA_DIR / "purchase_history.csv"

# Compradores ficticios de Helixa, uno por área. Cada categoría de proveedor (hoja Suppliers) tiene un área.
BUYERS = {
    "B1": {"name": "Lucía Herrera", "area": "APIs y excipientes",
           "categories": ["API", "Excipients", "Chemicals", "Single-use bioprocess", "Lab reagents"]},
    "B2": {"name": "Pablo Navarro", "area": "Envases",
           "categories": ["Primary packaging", "Secondary packaging"]},
    "B3": {"name": "Irene Campos", "area": "Logística y servicios",
           "categories": ["Logistics", "Services", "Consumables"]},
}


def buyer_for(category: str) -> str:
    """El comprador responsable de una categoría de proveedor."""
    return next(b for b, d in BUYERS.items() if category in d["categories"])
