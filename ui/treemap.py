"""Treemap «¿Dónde está el gasto en riesgo?»: gasto anual por categoría y proveedor, color = estado.

Para que destaque el gasto en riesgo:
- Cada proveedor con alerta tiene su casilla, con el color de su estado.
- Los proveedores sin riesgo de esa categoría se agrupan en una casilla neutra «Otros sin riesgo (N)».
- Las categorías sin ninguna alerta forman un único bloque neutro.
- Ninguna casilla baja del MIN_SHARE del lienzo, para que siempre quepa al menos el nombre. El tamaño deja
  de ser exactamente proporcional en las más pequeñas, pero el gasto real va escrito en cada una.

No usa Plotly: cada gráfico de Plotly cuesta ~100 ms en montarse en el navegador. La distribución
(algoritmo squarified) se calcula en Python y el navegador solo coloca botones HTML (st.components.v2,
sin iframe). Pulsar una casilla devuelve su ID a Python (setTriggerValue): un proveedor abre su ficha
y un grupo, la lista de sus proveedores. Cada casilla lleva el estado escrito y un aria-label completo.
"""
from __future__ import annotations

import html

import streamlit as st

from core.labels import CATEGORY_ES, short_supplier
from core.suppliers import load_suppliers

from . import theme as T
from .data import meur

W, H = 1000.0, 400.0          # lienzo nominal: el ancho real se escala en %, el alto es fijo en px
HEAD = 20.0                   # franja con el nombre de la categoría
PAD = 2.0
MIN_SHARE = 0.022             # área mínima de una casilla (fracción del lienzo): cabe el nombre
GROUP = "grp:"                # prefijo de las casillas que agrupan proveedores sin riesgo
REST = GROUP + "*"            # el bloque de las categorías sin ninguna alerta

# estado -> (texto, fondo, color del texto)
STATES = {
    "critica": ("Crítica", T.RED, "#FFFFFF"),
    "vigilar": ("Vigilar", T.AMBER_DOT, T.INK),
    "seguimiento": ("En seguimiento", "#D9C2EE", T.INK),
    "sin_riesgo": ("Sin riesgo", "#EEEDF2", T.MUTED),
}


def squarify(values: list[float], x: float, y: float, w: float, h: float) -> list[tuple[float, float, float, float]]:
    """Rectángulos (x, y, ancho, alto) con área proporcional a cada valor (ordenados de mayor a menor),
    lo más cuadrados posible (Bruls, Huizing y van Wijk, 2000)."""
    total = sum(values)
    if total <= 0 or w <= 0 or h <= 0:
        return [(x, y, 0.0, 0.0) for _ in values]
    areas = [v * w * h / total for v in values]

    def worst(row: list[float], side: float) -> float:
        s = sum(row)
        return max(max(side * side * r / (s * s), s * s / (side * side * r)) for r in row)

    out, i = [], 0
    while i < len(areas):
        side = min(w, h)
        row = [areas[i]]
        i += 1
        while i < len(areas) and worst(row + [areas[i]], side) <= worst(row, side):
            row.append(areas[i])
            i += 1
        s = sum(row)
        if w >= h:                               # columna a la izquierda
            cw, yy = s / h, y
            for a in row:
                out.append((x, yy, cw, a / cw))
                yy += a / cw
            x, w = x + cw, w - cw
        else:                                    # fila arriba
            rh, xx = s / w, x
            for a in row:
                out.append((xx, y, a / rh, rh))
                xx += a / rh
            y, h = y + rh, h - rh
    return out


def groups(states: dict[str, str]) -> list[tuple[str, list[tuple[str, float, list[str]]]]]:
    """[(categoría, [(id de la casilla, gasto, IDs de proveedores)])]. Una casilla es un proveedor con alerta,
    un grupo «otros sin riesgo» de su categoría o el bloque de las categorías sin alertas."""
    sup = load_suppliers()
    by_cat: dict[str, list] = {}
    for s in sup.values():
        if (s.annual_spend_eur or 0) > 0:
            by_cat.setdefault(s.category, []).append(s)
    out, rest = [], []
    for cat, ss in by_cat.items():
        risky = sorted((s for s in ss if s.id in states), key=lambda s: -s.annual_spend_eur)
        calm = [s for s in ss if s.id not in states]
        if not risky:
            rest += calm
            continue
        tiles = [(s.id, s.annual_spend_eur, [s.id]) for s in risky]
        if len(calm) == 1:
            tiles.append((calm[0].id, calm[0].annual_spend_eur, [calm[0].id]))
        elif calm:
            tiles.append((GROUP + cat, sum(s.annual_spend_eur for s in calm), [s.id for s in calm]))
        out.append((CATEGORY_ES.get(cat, cat), tiles))
    if rest:
        out.append((f"Otras {len({s.category for s in rest})} categorías",
                    [(REST, sum(s.annual_spend_eur for s in rest), [s.id for s in rest])]))
    return out


def _tile_text(tid: str, ids: list[str], state: str, spend: float, w: float, h: float) -> tuple[str, str, str]:
    """(tamaño, HTML, aria-label) de una casilla. Siempre lleva al menos el nombre."""
    sup = load_suppliers()
    label, _, _ = STATES[state]
    money = f"{meur(spend)} M€"
    if tid.startswith(GROUP):
        name = f"{'Otras categorías' if tid == REST else 'Otros'} sin riesgo ({len(ids)})"
        tag = "SIN RIESGO"
        aria = f"{name}: {money} de gasto anual. Pulsa para ver la lista."
    else:
        s = sup[tid]
        name, tag = short_supplier(s.name), label.upper()
        aria = f"{s.name} ({CATEGORY_ES.get(s.category, s.category)}): {label.lower()}, {money} de gasto anual. "                "Pulsa para ver la ficha."
    b = f"<b>{html.escape(name)}</b>"
    if w >= 105 and h >= 56:
        size, body = "lg", f"{b}<span class='s'>{tag}</span><span class='m'>{money}</span>"
    elif w >= 72 and h >= 38:
        size, body = "md", f"{b}<span class='s'>{tag}</span>"
    else:
        size, body = "sm", b
    return size, body, html.escape(aria)


def layout(states: dict[str, str]) -> dict:
    """Categorías y casillas en % del ancho y px del alto, con su texto, colores y aria-label."""
    total = sum(v for _, tiles in groups(states) for _, v, _ in tiles)
    floor = MIN_SHARE * total
    cats = [(name, [(tid, v, max(v, floor), ids) for tid, v, ids in tiles]) for name, tiles in groups(states)]
    cats.sort(key=lambda c: -sum(t[2] for t in c[1]))
    cat_rects = squarify([sum(t[2] for t in tiles) for _, tiles in cats], 0, 0, W, H)
    out_cats, out_tiles = [], []
    for (name, tiles), (cx, cy, cw, ch) in zip(cats, cat_rects):
        head = HEAD if ch > 2.6 * HEAD and cw > 60 else 0.0
        out_cats.append({"x": 100 * cx / W, "y": cy, "w": 100 * cw / W, "h": ch,
                         "label": html.escape(name) if head else ""})
        tiles = sorted(tiles, key=lambda t: -t[2])
        inner = squarify([t[2] for t in tiles], cx + PAD, cy + head, cw - 2 * PAD, ch - head - PAD)
        for (tid, spend, _, ids), (x, y, w, h) in zip(tiles, inner):
            state = "sin_riesgo" if tid.startswith(GROUP) else states.get(tid, "sin_riesgo")
            _, bg, fg = STATES[state]
            size, body, aria = _tile_text(tid, ids, state, spend, w, h)
            out_tiles.append({"id": tid, "x": 100 * x / W, "y": y, "w": 100 * w / W, "h": h, "bg": bg, "fg": fg,
                              "size": size, "html": body, "aria": aria, "ids": ids})
    return {"height": H, "cats": out_cats, "tiles": out_tiles}


CSS = f"""
.tm {{ position: relative; width: 100%; font-family: 'IBM Plex Sans', system-ui, sans-serif; }}
.cat {{ position: absolute; box-sizing: border-box; }}
.cat .cl {{ position: absolute; left: 4px; top: 2px; max-width: calc(100% - 8px); font-size: 12px; font-weight: 600;
  color: {T.MUTED}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tile {{ position: absolute; box-sizing: border-box; margin: 0; border: 2px solid #FFFFFF; border-radius: 5px;
  padding: 6px 8px; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; overflow: hidden;
  text-align: left; cursor: pointer; font: inherit; }}
.tile.sm {{ padding: 3px 5px; }}
.tile.sm b {{ font-size: 11px; }}
.tile:hover {{ box-shadow: inset 0 0 0 2px {T.PURPLE}; z-index: 2; }}
.tile:focus-visible {{ outline: 3px solid {T.PURPLE}; outline-offset: -3px; z-index: 3; }}
.tile b {{ max-width: 100%; font-size: 13px; line-height: 1.25; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }}
.tile .s {{ max-width: 100%; font-size: 11px; font-weight: 700; letter-spacing: .3px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }}
.tile .m {{ font-size: 12px; font-family: 'IBM Plex Mono', ui-monospace, monospace; }}
"""

JS = """
export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  const root = parentElement.querySelector('.tm');
  if (!root || !data) return;
  root.replaceChildren();
  root.style.height = data.height + 'px';
  const place = (el, r) => {
    el.style.left = r.x + '%'; el.style.top = r.y + 'px'; el.style.width = r.w + '%'; el.style.height = r.h + 'px';
  };
  for (const c of data.cats) {
    const d = document.createElement('div');
    d.className = 'cat';
    place(d, c);
    d.innerHTML = '<span class="cl">' + c.label + '</span>';
    root.appendChild(d);
  }
  for (const t of data.tiles) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tile ' + t.size;
    place(b, t);
    b.style.background = t.bg;
    b.style.color = t.fg;
    b.title = t.aria;
    b.setAttribute('aria-label', t.aria);
    b.innerHTML = t.html;
    b.onclick = () => setTriggerValue('picked', t.id);
    root.appendChild(b);
  }
}
"""

_component = st.components.v2.component("spend_treemap", html='<div class="tm" role="group" '
                                        'aria-label="Gasto anual por categoría y proveedor"></div>', css=CSS, js=JS)


@st.cache_data(show_spinner=False)
def _layout(states: dict[str, str]) -> dict:
    return layout(states)


def spend_treemap(states: dict[str, str], key: str) -> str | None:
    """Dibuja el treemap y devuelve el ID de la casilla pulsada en este clic: un proveedor o un grupo
    (GROUP + categoría, o REST). None si no se ha pulsado nada."""
    res = _component(data=_layout(states), key=key, height=int(H), on_picked_change=lambda: None)
    return res.picked if res is not None else None
