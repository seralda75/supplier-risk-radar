"""Esquemas Pydantic de la salida del juez LLM.

Regla: cada campo con una description clara -> el LLM rellena mucho mejor.
El JSON schema de estos modelos se pasa a Ollama en `format`, así que la salida
ya llega con la forma correcta; Pydantic valida rangos y formato de los IDs.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Taxonomía genérica de riesgos de suministro. Las del enunciado + categorías habituales
# en cualquier mapa de riesgos (ciberataque, cortes de suministro eléctrico, escasez de
# materia prima, conflicto geopolítico) + un cajón de sastre para no forzar etiquetas.
EventType = Literal[
    "fire_plant_incident", "natural_disaster", "labour_strike", "logistics_disruption",
    "regulatory_action", "quality_recall", "export_restriction", "financial_distress",
    "acquisition", "leadership_change", "cyber_incident", "utility_outage",
    "supply_shortage", "geopolitical_conflict", "other_risk",
    "positive_news", "not_relevant",
]

# Nombre legible (estilo de la columna Event_Type del entrenamiento)
EVENT_LABELS: dict[str, str] = {
    "fire_plant_incident": "Fire / plant incident",
    "natural_disaster": "Natural disaster",
    "labour_strike": "Labour strike",
    "logistics_disruption": "Logistics disruption",
    "regulatory_action": "Regulatory action",
    "quality_recall": "Quality recall",
    "export_restriction": "Export restriction",
    "financial_distress": "Financial distress",
    "acquisition": "Acquisition by competitor",
    "leadership_change": "Leadership change",
    "cyber_incident": "Cyber incident",
    "utility_outage": "Utility outage",
    "supply_shortage": "Supply shortage",
    "geopolitical_conflict": "Geopolitical conflict",
    "other_risk": "Other risk",
    "positive_news": "Positive news",
    "not_relevant": "Not relevant",
}

_ID_RE = re.compile(r"^S\d{3}$")


class NewsAssessment(BaseModel):
    """Veredicto del juez LLM sobre una noticia.

    Todos los campos son obligatorios (sin default): si no, el JSON schema los marca como
    opcionales y los modelos pequeños se los saltan. El orden importa: primero la evidencia
    y los afectados, después las decisiones (el modelo "razona" antes de decidir).
    """
    evidence: str = Field(..., description="Frase literal de la noticia que justifica la decisión")
    affected_ids: list[str] = Field(..., description="IDs de proveedor (S001...) afectados o de los que "
                                                     "habla la noticia. Solo de la lista de candidatos; "
                                                     "lista vacía si ninguno")
    event_type: EventType = Field(..., description="Tipo de evento")
    is_risk: bool = Field(..., description="True si el evento puede impedir o retrasar el suministro "
                                           "de algún proveedor de Helixa")
    severity: int = Field(..., ge=1, le=5, description="Gravedad del evento: 1 = sin impacto, "
                                                       "5 = para la producción del proveedor")
    stops_supply_soon: bool = Field(..., description="True si puede parar o retrasar seriamente el "
                                                     "suministro en los próximos días o semanas")
    recovery_days: Optional[int] = Field(..., ge=0, description="Días estimados hasta que el proveedor "
                                                                "se recupere según la noticia; null si "
                                                                "no se puede estimar o no aplica")
    confidence: float = Field(..., ge=0, le=1, description="Seguridad global, número decimal entre 0.0 y 1.0")

    @field_validator("confidence", mode="before")
    @classmethod
    def _percent_to_unit(cls, v):
        # Ollama no impone rangos numéricos: algunos modelos devuelven 80 en vez de 0.8
        if isinstance(v, (int, float)) and 1 < v <= 100:
            return v / 100
        return v

    @field_validator("affected_ids")
    @classmethod
    def _normalize_ids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for x in v:
            x = x.strip().upper()
            if _ID_RE.match(x) and x not in out:
                out.append(x)
        return out
