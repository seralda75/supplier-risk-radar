"""Carga de las noticias de los tres Excel del reto con un formato común."""
from __future__ import annotations

from typing import Literal

import pandas as pd

from .config import TEST_XLSX, TRAIN_XLSX, VALIDATION_XLSX

Split = Literal["train", "validation", "test"]
SHEETS = {"train": (TRAIN_XLSX, "News"), "validation": (VALIDATION_XLSX, "News_Validation"),
          "test": (TEST_XLSX, "News_Test")}
LABEL_COLS = ["Is_Risk", "Urgent", "Affected_Supplier_IDs", "Event_Type", "Explanation"]


def parse_ids(value) -> list[str]:
    """'S003; S007' -> ['S003', 'S007'];  vacío/NaN -> []."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return []
    return [x.strip() for x in str(value).replace(",", ";").split(";") if x.strip()]


def format_ids(ids: list[str]) -> str:
    """Formato exacto de la entrega: IDs ordenados separados por '; ' (o cadena vacía)."""
    return "; ".join(sorted(set(ids)))


def load_news(split: Split) -> list[dict]:
    """Noticias como lista de dicts. Las de train/validation incluyen las etiquetas."""
    path, sheet = SHEETS[split]
    df = pd.read_excel(path, sheet_name=sheet)
    out = []
    for r in df.to_dict("records"):
        item = {
            "News_ID": r["News_ID"],
            "Published_Date": pd.to_datetime(r["Published_Date"]).date().isoformat(),
            "Source": r.get("Source", ""),
            "Headline": r["Headline"],
            "Summary": r.get("Summary", "") if not pd.isna(r.get("Summary", "")) else "",
        }
        if split != "test":
            item.update({
                "Is_Risk": r["Is_Risk"], "Urgent": r["Urgent"],
                "Affected_Supplier_IDs": parse_ids(r["Affected_Supplier_IDs"]),
                "Event_Type": r["Event_Type"], "Explanation": r["Explanation"],
            })
        out.append(item)
    return out
