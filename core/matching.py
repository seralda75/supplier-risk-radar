"""Generación de candidatos: ¿de qué proveedores podría hablar esta noticia?

Determinista, gratis y escalable a cientos de proveedores. Objetivo: RECALL alto (que no se
escape ningún afectado). La precisión la pone después el juez LLM (o las reglas en --no-llm).

Cada candidato lleva sus motivos (evidencia), por ejemplo:
  S014  name:ambiguous 'gujarat minerals' | location:region 'gujarat' | location:city 'vadodara'
Los motivos de tipo `name:ambiguous` (solo una parte del nombre: "Lumina", "Celtic",
"Sunrise"...) obligan a verificar la identidad: puede ser una película o un equipo de fútbol.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz

from .suppliers import (CATEGORY_ALIASES, COUNTRY_ALIASES, MATERIAL_ALIASES, SUPPLIER_ROUTES, Supplier,
                        load_suppliers)

# Puntuación de cada tipo de motivo
SCORES = {
    ("name", "full"): 1.0, ("name", "fuzzy"): 0.95, ("name", "ambiguous"): 0.6,
    ("location", "city"): 0.8, ("location", "region"): 0.7, ("location", "river"): 0.6,
    ("route", "route"): 0.6, ("location", "country+material"): 0.8, ("location", "country"): 0.3,
    ("material", "material"): 0.4, ("category", "category"): 0.2,
}
MAX_CANDIDATES = 10
FUZZY_NAME_MIN = 92          # rapidfuzz partial_ratio mínimo para aceptar un nombre con erratas

# Sufijos societarios que no identifican a la empresa
LEGAL_SUFFIXES = {"ltd", "gmbh", "spa", "ag", "as", "inc", "co", "sl", "sp", "z", "o", "llc", "plc", "sa", "bv",
                  "nv", "srl", "kg", "corp", "corporation", "limited"}
# Primeras palabras que por sí solas no identifican a un proveedor (además de los topónimos)
GENERIC_WORDS = {"pacific", "nordic", "alpine", "andes", "benelux", "iberia", "lombardia", "valley", "north",
                 "south", "east", "west", "global", "international", "the"}
# Palabras que indican contexto farmacéutico (para aceptar un nombre ambiguo en modo reglas)
PHARMA_CONTEXT = ["pharma", "pharmaceutical", "pharmaceuticals", "drug", "drugs", "drugmaker", "medicine",
                  "medicines", "biotech", "biologics", "life sciences", "FDA", "EMA", "GMP", "active ingredient",
                  "excipient", "packaging", "vials", "laboratory", "clinical", "vaccine"]


# ---------------------------------------------------------------------------
# Normalización de texto
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """minúsculas, sin tildes, '&' -> 'and', y todo lo que no sea letra o número -> espacio."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower().replace("&", " and ")
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", text).split()) + " "


def _is_acronym(alias: str) -> bool:
    return alias.replace(".", "").isupper()


def contains(alias: str, raw: str, norm: str) -> bool:
    """¿Aparece el alias como palabra o frase completa? Los acrónimos (US, FDA, LNP) distinguen mayúsculas."""
    if _is_acronym(alias):
        return re.search(r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z])", raw) is not None
    a = normalize(alias)
    return a.strip() != "" and a in norm


def first_match(aliases: list[str], raw: str, norm: str) -> str | None:
    return next((a for a in aliases if contains(a, raw, norm)), None)


# ---------------------------------------------------------------------------
# Nombres de proveedor
# ---------------------------------------------------------------------------

def core_name(name: str) -> str:
    """'Polaris Films Sp. z o.o.' -> 'polaris films';  'Iberia Starch & Sugars' -> 'iberia starch and sugars'."""
    tokens = normalize(name).split()
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


@lru_cache(maxsize=1)
def _generic_tokens() -> frozenset[str]:
    """Topónimos del diccionario geográfico + palabras comunes: no bastan para identificar a un proveedor."""
    words = set(GENERIC_WORDS)
    for s in load_suppliers().values():
        places = s.geo.get("aliases", []) + s.geo.get("regions", []) + s.geo.get("rivers", [])
        places += [s.city, s.country] + COUNTRY_ALIASES.get(s.country, [])
        for p in places:
            words.update(normalize(p).split())
    return frozenset(words)


def brand(name: str) -> str:
    """Parte corta del nombre con la que la prensa suele citar a la empresa: la primera palabra,
    o las primeras hasta incluir una que no sea un topónimo ('Gujarat Minerals', 'Lumina')."""
    tokens = core_name(name).split()
    generic = _generic_tokens()
    for i, t in enumerate(tokens):
        if t not in generic:
            return " ".join(tokens[: i + 1])
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Candidatos
# ---------------------------------------------------------------------------

@dataclass
class Reason:
    kind: str     # name | location | route | material | category
    level: str    # full | fuzzy | ambiguous | city | region | river | country | country+material | ...
    alias: str    # el texto que ha coincidido

    @property
    def score(self) -> float:
        return SCORES[(self.kind, self.level)]

    def __str__(self) -> str:
        return f"{self.kind}:{self.level} '{self.alias}'"


@dataclass
class Candidate:
    supplier: Supplier
    reasons: list[Reason] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.supplier.id

    @property
    def score(self) -> float:
        # el mejor motivo + un pequeño extra si hay varios tipos de evidencia distintos
        kinds = {r.kind for r in self.reasons}
        return round(max(r.score for r in self.reasons) + 0.05 * (len(kinds) - 1), 3)

    def has(self, kind: str, *levels: str) -> bool:
        return any(r.kind == kind and (not levels or r.level in levels) for r in self.reasons)

    @property
    def named(self) -> bool:
        """El nombre completo aparece en la noticia (identidad casi segura)."""
        return self.has("name", "full", "fuzzy")

    @property
    def ambiguous_name(self) -> bool:
        """Solo aparece una parte del nombre: hay que verificar que es este proveedor."""
        return self.has("name", "ambiguous") and not self.named

    @property
    def specific_location(self) -> bool:
        """Coincide por ciudad, región, río o ruta (más concreto que el país)."""
        return self.has("location", "city", "region", "river", "country+material") or self.has("route")

    def evidence(self) -> str:
        return " | ".join(str(r) for r in self.reasons)


def _supplier_reasons(s: Supplier, raw: str, norm: str) -> list[Reason]:
    reasons: list[Reason] = []

    # 1) Nombre: completo, con erratas (rapidfuzz) o solo la marca (ambiguo)
    core = core_name(s.name)
    if f" {core} " in norm:
        reasons.append(Reason("name", "full", core))
    elif len(core) >= 10 and fuzz.partial_ratio(core, norm) >= FUZZY_NAME_MIN:
        reasons.append(Reason("name", "fuzzy", core))
    else:
        b = brand(s.name)
        if b != core and f" {b} " in norm:
            reasons.append(Reason("name", "ambiguous", b))

    # 2) Ubicación: ciudad > región > río > país
    if a := first_match(s.geo.get("aliases", []) + [s.city], raw, norm):
        reasons.append(Reason("location", "city", a))
    if a := first_match(s.geo.get("regions", []), raw, norm):
        reasons.append(Reason("location", "region", a))
    if a := first_match(s.geo.get("rivers", []), raw, norm):
        reasons.append(Reason("location", "river", a))
    if a := first_match(SUPPLIER_ROUTES.get(s.id, []), raw, norm):
        reasons.append(Reason("route", "route", a))

    # 3) Material y categoría
    mat = first_match(MATERIAL_ALIASES.get(s.material, []), raw, norm)
    if mat:
        reasons.append(Reason("material", "material", mat))
    cat = first_match(CATEGORY_ALIASES.get(s.category, []), raw, norm)
    if cat:
        reasons.append(Reason("category", "category", cat))

    country = first_match(COUNTRY_ALIASES.get(s.country, [s.country]), raw, norm)
    if country:
        # país + material/categoría ("India restringe la exportación de paracetamol") es casi tan fuerte como la ciudad
        level = "country+material" if (mat or cat) else "country"
        reasons.append(Reason("location", level, country))
    return reasons


def find_candidates(headline: str, summary: str = "", max_candidates: int = MAX_CANDIDATES) -> list[Candidate]:
    """Devuelve los proveedores que podrían estar implicados, ordenados por puntuación."""
    raw = f"{headline}. {summary}"
    norm = normalize(raw)
    cands = []
    for s in load_suppliers().values():
        reasons = _supplier_reasons(s, raw, norm)
        # La categoría sola no basta para ser candidato ("chemical" aparece en muchas noticias)
        if reasons and any(r.kind != "category" for r in reasons):
            cands.append(Candidate(s, reasons))

    # Si en un país ya hay coincidencias concretas (ciudad, región...), las coincidencias solo por
    # país de ese mismo país sobran: "terremoto en el sur de Taiwán" no implica a Hsinchu.
    specific_countries = {c.supplier.country for c in cands if c.specific_location}
    cands = [c for c in cands
             if not (c.supplier.country in specific_countries and _only_country(c))]
    cands.sort(key=lambda c: (-c.score, c.id))
    return cands[:max_candidates]


def _only_country(c: Candidate) -> bool:
    """El único vínculo con la noticia es el país (o país + palabras de categoría)."""
    return all(r.kind == "category" or (r.kind == "location" and r.level == "country") for r in c.reasons)


def has_context_support(c: Candidate, headline: str, summary: str = "") -> bool:
    """Para un nombre ambiguo: ¿hay algo más en la noticia que apunte a ESTE proveedor?
    (su material, su ciudad/región o vocabulario farmacéutico). 'Celtic beat Rangers' -> no."""
    if c.named:
        return True
    if c.has("material") or c.has("location", "city", "region", "country+material") or c.has("route"):
        return True
    raw = f"{headline}. {summary}"
    return first_match(PHARMA_CONTEXT, raw, normalize(raw)) is not None
