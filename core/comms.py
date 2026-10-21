"""Agente de comunicaciones: a partir de una alerta, dos borradores editables.

- Correo al proveedor afectado, en inglés: pide el estado de la situación y la fecha de reanudación (y una
  asignación parcial si el plan la prevé). No revela el stock ni el margen de Helixa.
- Nota interna para el equipo, en español: resumen, impacto (medicamentos, días de margen, gasto) y plan.

La IA local (Ollama) redacta el texto libre: el correo y el resumen de la nota. Las secciones con cifras de
la nota (impacto y plan) las monta el código con los datos de la alerta (Facts): una cifra nunca depende de
la IA. Después se comprueba el texto de la IA (issues): todas sus cifras están en los datos, el correo no
revela el stock, el margen ni el gasto, y la asignación parcial aparece solo si el plan la prevé. Si algo
falla, se pide otra redacción y, si vuelve a fallar, se usa la plantilla. Sin Ollama, la plantilla.
Nada se envía: el panel solo registra en la auditoría que el comprador lo ha marcado como enviado.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from .actions import Step


class Drafts(BaseModel):
    email_subject: str = Field(description="Subject of the email to the supplier, in English")
    email_body: str = Field(description="Body of the email to the supplier, in English, signed by Helixa Procurement")
    note: str = Field(description="Internal note for the Helixa team, in Spanish")


@dataclass
class Facts:
    """Todo lo que los borradores pueden decir. Cualquier cifra que no salga de aquí es inventada."""
    supplier: str
    material_en: str
    material_es: str
    products_en: list[str]
    products_es: list[str]
    event_en: str
    headline: str
    source: str
    date: str
    level_es: str                  # «crítica», «en vigilancia (riesgo latente)», «en seguimiento semanal»
    what_es: str                   # «qué pasa», en dos frases
    inventory_days: float | None
    recovery_days: int
    recovery_estimated: bool
    margin_days: float
    spend_meur: str                # «2,6»
    dependency_es: str             # «proveedor único» / «alternativo aprobado: Kaveri Fine Chemicals»
    steps: list[Step] = field(default_factory=list)
    ask_partial: bool = False      # el plan pide al proveedor una asignación parcial

    def text(self) -> str:
        """Los datos en texto (el prompt de la IA y la lista de cifras permitidas salen de aquí)."""
        stock = ("no safety stock (immediate impact)" if self.inventory_days is None
                 else f"{self.inventory_days:.0f} days of stock")
        plan = "\n".join(f"  {i}. {s.text} ({s.owner} · {s.when})" for i, s in enumerate(self.steps, 1))
        return (f"Supplier: {self.supplier}\nMaterial: {self.material_en} (ES: {self.material_es})\n"
                f"Medicines (EN): {', '.join(self.products_en) or 'none'}\n"
                f"Medicines (ES): {', '.join(self.products_es) or 'ninguno'}\n"
                f"Event: {self.event_en}\nNews: \"{self.headline}\" ({self.source}, {self.date})\n"
                f"Alert level (ES): {self.level_es}\nWhat happens (ES): {self.what_es}\n"
                f"Helixa stock: {stock}\nRecovery time: {self.recovery_days} days"
                f"{' (estimated)' if self.recovery_estimated else ' (from the news)'}\n"
                f"Margin: {_signed(self.margin_days)} days\nAnnual spend with the supplier: {self.spend_meur} M€\n"
                f"Dependency (ES): {self.dependency_es}\n"
                f"Ask the supplier for a partial allocation: {'yes' if self.ask_partial else 'no'}\n"
                f"Plan (ES):\n{plan}")


def _signed(x: float) -> str:
    v = round(x)
    return f"+{v}" if v > 0 else ("0" if v == 0 else f"−{abs(v)}")


# ---------------------------------------------------------------------------
# Comprobación de cifras
# ---------------------------------------------------------------------------

_NUM = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*")


def numbers(text: str) -> set[float]:
    """Cifras de un texto, normalizadas: «2,6» = «2.6», «1.800» = «1,800», «−44» = 44 (el signo da igual)."""
    out = set()
    for m in _NUM.findall(text or ""):
        parts = re.split(r"[.,]", m)
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):     # separador de miles
            out.add(float("".join(parts)))
        else:
            out.add(float(m.replace(",", ".")))
    return out


_LIST = re.compile(r"^\s*\d+[.)]\s", re.M)        # «1. », «2) » al principio de una línea


def figures(text: str, f: Facts) -> set[float]:
    """Cifras de un texto sin contar la fecha exacta de la noticia ni la numeración de una lista: así la fecha
    no hace pasar por buenos un «9» o un «17», ni el paso 3 del plan un «en 3 días»."""
    text = text or ""
    if f.date:
        text = text.replace(f.date, " ")
    return numbers(_LIST.sub(" ", text))


def allowed(f: Facts) -> set[float]:
    """Cifras permitidas: las de los datos de la alerta."""
    return figures(f.text(), f)


def extra(text: str, f: Facts) -> list[str]:
    """Cifras de un texto que no están en los datos de la alerta (lista vacía = todo bien)."""
    return [f"{x:g}" for x in sorted(figures(text, f) - allowed(f))]


def check(d: Drafts, f: Facts) -> list[str]:
    """Cifras de los borradores que no están en los datos de la alerta (lista vacía = todo bien)."""
    return extra(f"{d.email_subject}\n{d.email_body}\n{d.note}", f)


# ---------------------------------------------------------------------------
# Plantilla (sin IA, o si la IA inventa cifras)
# ---------------------------------------------------------------------------

def template(f: Facts) -> Drafts:
    partial = (f"\n- whether you could offer a partial allocation of {f.material_en} while supply is constrained;"
               if f.ask_partial else "")
    body = (f"Dear {f.supplier} team,\n\n"
            f"We have seen the report \"{f.headline}\" ({f.source}, {f.date}). As you supply Helixa "
            f"Pharmaceuticals with {f.material_en}, we would like to understand the impact on our orders.\n\n"
            "Could you please confirm:\n"
            "- the current status of your production and of the shipments to Helixa;\n"
            f"- the expected date on which normal supply will resume;{partial}\n\n"
            "Thank you in advance for your prompt reply.\n\n"
            "Kind regards,\nProcurement team · Helixa Pharmaceuticals")
    if f.inventory_days is None:
        margin = f"sin stock de reserva: impacto inmediato durante {f.recovery_days} días"
    else:
        margin = (f"{_signed(f.margin_days)} días ({f.inventory_days:.0f} días de stock frente a {f.recovery_days} "
                  f"días de recuperación{' estimada' if f.recovery_estimated else ''})")
    plan = "\n".join(f"{i}. {s.text} ({s.owner} · {s.when})" for i, s in enumerate(f.steps, 1))
    note = (f"Alerta {f.level_es} · {f.supplier} ({f.material_es})\n\n"
            f"Resumen: {f.what_es} Fuente: {f.source}, {f.date}: «{f.headline}».\n\n"
            "Impacto:\n"
            f"- Medicamentos: {', '.join(f.products_es) or 'ninguno (servicio sin medicamentos asociados)'}\n"
            f"- Días de margen: {margin}\n"
            f"- Gasto anual con el proveedor: {f.spend_meur} M€ ({f.dependency_es})\n\n"
            f"Plan recomendado:\n{plan}\n\n"
            "Siguiente paso: pedir al proveedor el estado de la situación y la fecha de reanudación.")
    return Drafts(email_subject=f"{f.material_en}: current status and expected restart date", email_body=body,
                  note=note)


# ---------------------------------------------------------------------------
# Redacción con la IA local
# ---------------------------------------------------------------------------

class Written(BaseModel):
    """Lo que redacta la IA: solo texto. Las cifras de la nota (impacto y plan) las pone el código."""
    email_subject: str = Field(description="Subject of the email to the supplier, in English")
    email_body: str = Field(description="Body of the email to the supplier, in English, without the subject line")
    summary_es: str = Field(description="One or two sentences in Spanish: what happens and why it matters")


SYSTEM = ("You are the communications assistant of the procurement team at Helixa Pharmaceuticals. You write "
          "clear, professional, short drafts. You use ONLY the facts you are given: never add numbers, dates, "
          "quantities, prices or deadlines that are not in the facts.")

INSTRUCTIONS = """Write, from the facts below:

1. email_subject and email_body: a short email IN ENGLISH (at most 110 words) to {supplier}. Ask for the current
   status of the situation and the expected date on which normal supply will resume.{partial}
   Do NOT mention Helixa's stock, margin or spend. Do not repeat the subject inside the body.
   Sign as "Procurement team · Helixa Pharmaceuticals".
2. summary_es: one or two sentences IN SPANISH (at most 45 words) for the internal note: what happens and
   which medicines are at risk. No figures other than those in the facts.

FACTS FOR THE EMAIL
Supplier: {supplier}
Material we buy from them: {material}
Medicines that use it: {products}
Event: {event}
News: "{headline}" ({source}, {date})

FACTS FOR THE SPANISH SUMMARY
{what_es}
Medicamentos: {products_es}"""

PARTIAL_YES = " Also ask whether they can offer a partial allocation while supply is constrained."
PARTIAL_NO = " Do not ask for a partial allocation."


def _prompt(f: Facts, bad: list[str]) -> str:
    p = INSTRUCTIONS.format(supplier=f.supplier, partial=PARTIAL_YES if f.ask_partial else PARTIAL_NO,
                            material=f.material_en, products=", ".join(f.products_en) or "none (service)",
                            event=f.event_en, headline=f.headline, source=f.source, date=f.date, what_es=f.what_es,
                            products_es=", ".join(f.products_es) or "ninguno")
    if bad:
        p += f"\n\nYour previous draft had these problems: {'; '.join(bad)}. Fix them."
    return p


def _clean_body(body: str) -> str:
    """Quita una línea «Subject: …» si la IA la repite dentro del cuerpo."""
    lines = body.strip().splitlines()
    while lines and lines[0].lower().startswith("subject:"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def issues(w: Written, f: Facts) -> list[str]:
    """Problemas del texto de la IA (lista vacía = se puede usar):
    - cifras que no están en los datos de la alerta;
    - el correo revela el stock, el margen o el gasto de Helixa;
    - pide una asignación parcial que el plan no prevé (o no la pide cuando sí)."""
    out = []
    bad = extra(f"{w.email_subject}\n{w.email_body}\n{w.summary_es}", f)
    if bad:
        out.append("figures not in the facts: " + ", ".join(bad))
    internal = {abs(round(f.margin_days)), float(f.spend_meur.replace(",", "."))}
    if f.inventory_days is not None:
        internal.add(round(f.inventory_days))
    leaked = figures(f"{w.email_subject}\n{w.email_body}", f) & {float(x) for x in internal}
    if leaked:
        out.append("the email reveals internal figures: " + ", ".join(f"{x:g}" for x in sorted(leaked)))
    asks = "partial allocation" in w.email_body.lower()
    if asks != f.ask_partial:
        out.append("ask for a partial allocation" if f.ask_partial else "do not mention a partial allocation")
    return out


@dataclass
class Prepared:
    drafts: Drafts
    source: str                 # "ia" | "plantilla"
    reason: str                 # por qué la plantilla, o vacío
    seconds: float
    attempts: int


def prepare(f: Facts, use_llm: bool = True, fresh: bool = False) -> Prepared:
    """Borradores para una alerta. La IA redacta el correo y el resumen; el código pone el impacto y el plan
    de la nota (con las cifras de la alerta). Si el texto de la IA tiene problemas (issues), se le pide otra
    redacción; si vuelve a fallar, o no hay IA, se usa la plantilla entera. fresh=True: sin la caché del LLM
    (para medir la latencia real)."""
    t0 = time.perf_counter()
    if not use_llm:
        return Prepared(template(f), "plantilla", "la IA local no está disponible", time.perf_counter() - t0, 0)
    from . import llm
    bad: list[str] = []
    for attempt in (1, 2):
        try:
            w = llm.extract(_prompt(f, bad), Written, system=SYSTEM, use_cache=attempt == 1 and not fresh)
        except Exception as e:                        # Ollama caído a mitad, JSON inválido tras los reintentos
            return Prepared(template(f), "plantilla", f"la IA local falló ({type(e).__name__})",
                            time.perf_counter() - t0, attempt)
        w = w.model_copy(update={"email_body": _clean_body(w.email_body)})
        bad = issues(w, f)
        if not bad:
            t = template(f)
            note = t.note.replace(f"Resumen: {f.what_es}", f"Resumen: {w.summary_es.strip()}", 1)
            return Prepared(Drafts(email_subject=w.email_subject.strip(), email_body=w.email_body, note=note),
                            "ia", "", time.perf_counter() - t0, attempt)
    return Prepared(template(f), "plantilla", "el borrador de la IA no pasó la comprobación (" + "; ".join(bad) + ")",
                    time.perf_counter() - t0, 2)
