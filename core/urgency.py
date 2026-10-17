"""Urgencia = gravedad del evento × dependencia del proveedor.

Lo que dice el README: Urgent = Y si el evento puede parar o retrasar seriamente el suministro
pronto; para decidir, pensar en la gravedad y en la dependencia (proveedor único, criticidad,
cobertura de inventario).

Lo que enseña el entrenamiento: manda la gravedad del evento. La inundación de Gujarat es urgente
aunque ninguno de los tres proveedores sea único; la huelga de camioneros no lo es aunque afecte
a S011, que sí lo es. Por eso la dependencia actúa como desempate en los eventos de gravedad
intermedia (3): un incendio moderado en un proveedor único sí es urgente; en uno con alternativo
cualificado y stock, puede esperar al informe semanal.

Los umbrales son constantes visibles: el cliente puede ajustarlos según su apetito de riesgo.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schemas import NewsAssessment
from .suppliers import Supplier

SEVERITY_URGENT = 4          # gravedad a partir de la cual es urgente si para el suministro pronto
SEVERITY_BORDERLINE = 3      # gravedad intermedia: urgente solo si la dependencia es alta
DEPENDENCY_HIGH = 0.6        # dependencia a partir de la cual se considera alta


@dataclass
class Dependency:
    supplier_id: str
    score: float             # 0 (fácil de sustituir) - 1 (sin él se para la producción)
    factors: list[str]


def dependency(s: Supplier) -> Dependency:
    """Puntuación de dependencia de Helixa respecto a un proveedor (0-1), con sus factores."""
    score, factors = 0.0, []
    if s.single_source:
        score += 0.4
        factors.append("proveedor único")
    else:
        factors.append(f"alternativo {s.alternate_id}" if s.alternate_id else "sin alternativo registrado")
    crit = {"High": 0.3, "Medium": 0.15}.get(s.criticality, 0.0)
    score += crit
    factors.append(f"criticidad {s.criticality}")
    inv = s.inventory_cover_days
    if inv is None:
        score += 0.1         # servicios y logística: sin colchón de inventario conocido
        factors.append("sin inventario de reserva (servicio)")
    else:
        score += 0.2 if inv <= 30 else 0.1 if inv <= 45 else 0.0
        factors.append(f"{inv:.0f} días de inventario")
    return Dependency(s.id, round(min(score, 1.0), 2), factors)


def is_urgent(a: NewsAssessment, deps: list[Dependency]) -> tuple[bool, str]:
    """Decide la urgencia y devuelve también el motivo (para la explicación y la auditoría)."""
    if not a.is_risk or not a.affected_ids:
        return False, "no es un riesgo"
    if not a.stops_supply_soon:
        return False, "efecto lento o limitado: puede esperar al informe semanal"
    max_dep = max((d.score for d in deps), default=0.0)
    if a.severity >= SEVERITY_URGENT:
        return True, f"evento grave (gravedad {a.severity}/5) que puede parar el suministro pronto"
    if a.severity >= SEVERITY_BORDERLINE and max_dep >= DEPENDENCY_HIGH:
        return True, (f"gravedad {a.severity}/5 con dependencia alta ({max_dep:.2f}): "
                      "no hay margen para esperar")
    return False, f"gravedad {a.severity}/5 con dependencia {max_dep:.2f}: impacto limitado o con alternativa"
