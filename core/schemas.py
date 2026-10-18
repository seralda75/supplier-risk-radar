"""Esquemas Pydantic de la salida del juez LLM.

Regla: cada campo con una description clara -> el LLM rellena mucho mejor.
El JSON schema de estos modelos se pasa a Ollama en `format`, así que la salida
ya llega con la forma correcta; Pydantic valida rangos y formato de los IDs.
"""
from __future__ import annotations

import math
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

# Nombre en español para las explicaciones y el panel
EVENT_LABELS_ES: dict[str, str] = {
    "fire_plant_incident": "incendio / incidente en planta",
    "natural_disaster": "desastre natural",
    "labour_strike": "huelga",
    "logistics_disruption": "interrupción logística",
    "regulatory_action": "acción regulatoria",
    "quality_recall": "retirada por calidad",
    "export_restriction": "restricción a la exportación",
    "financial_distress": "dificultades financieras",
    "acquisition": "adquisición por un competidor",
    "leadership_change": "cambio en la dirección",
    "cyber_incident": "ciberataque / incidente informático",
    "utility_outage": "corte de suministros básicos",
    "supply_shortage": "escasez de suministro",
    "geopolitical_conflict": "conflicto geopolítico",
    "other_risk": "otro riesgo",
    "positive_news": "noticia positiva",
    "not_relevant": "no relevante",
}

_ID_RE = re.compile(r"^S\d{3}$")


RecoveryUnit = Literal["hours", "days", "weeks", "months"]
DAYS_PER_UNIT = {"hours": 1 / 24, "days": 1, "weeks": 7, "months": 30}


def to_days(value: float | None, unit: str | None) -> int | None:
    """Convierte la duración de la noticia a días enteros, redondeando hacia arriba (48 horas -> 2).
    Sin unidad se asume días (lo más habitual en las noticias)."""
    if value is None:
        return None
    return math.ceil(round(value * DAYS_PER_UNIT.get(unit or "days", 1), 6))


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
    # Duración tal como la dice la noticia; el código la pasa a días (recovery_days). Antes se pedían
    # días directamente y el LLM copiaba el número sin convertir ("48-hour strike" -> 48 días).
    recovery_value: Optional[float] = Field(..., ge=0, description=(
        "Number in the article for how long until the supplier is back to normal, exactly as written "
        "('48-hour strike' -> 48, 'three weeks' -> 3); null if the article gives no duration"))
    recovery_unit: Optional[RecoveryUnit] = Field(..., description=(
        "Unit of recovery_value exactly as written in the article; null if recovery_value is null"))
    # En inglés, como el prompt: el modelo lee esta descripción en el JSON schema de `format`.
    # Antes decía solo "Seguridad global" y qwen2.5 mezclaba escalas (80, pero también 3 o 4 como si
    # fuera una nota de 1 a 5); ver docs/evaluacion.md, v6.
    confidence: float = Field(..., ge=0, le=1, description=(
        "How sure you are that YOUR ANSWER (is_risk and affected_ids) is correct, as a decimal between "
        "0.0 and 1.0, e.g. 0.9. It is not the probability of a risk and not a 1-5 score: a clear "
        "non-risk answer also gets a high confidence."))

    @property
    def recovery_days(self) -> int | None:
        """Días hasta la recuperación, convertidos por código (el LLM no hace la cuenta)."""
        return to_days(self.recovery_value, self.recovery_unit)

    @field_validator("confidence", mode="before")
    @classmethod
    def _percent_to_unit(cls, v):
        # Ollama no impone rangos numéricos. 80 es claramente un porcentaje (-> 0.8); un valor entre
        # 1 y 5 es ambiguo (¿3 %? ¿3 sobre 5?): se rechaza y extract() reintenta con este mensaje
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if 5 < v <= 100:
                return v / 100
            if 1 < v <= 5:
                raise ValueError("confidence must be a decimal between 0.0 and 1.0 (e.g. 0.85), "
                                 "not a 1-5 score or a percentage")
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
