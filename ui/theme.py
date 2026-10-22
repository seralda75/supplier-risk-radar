"""Estilo del panel, copiado de docs/mockup_centro_control.html (colores, tipografía, radios y espaciados).

Las fuentes IBM Plex se sirven desde static/fonts (ver .streamlit/config.toml): sin Google Fonts.
Los widgets de Streamlit que hacen falta (navegación, botones, formularios) se visten con su clase
`st-key-<key>`, que Streamlit añade a cada elemento con `key`. Todo el CSS es una constante que app.py
inyecta en una sola llamada; la entrada activa del menú se marca con su clave (navon-<vista>).
"""
from __future__ import annotations

from urllib.parse import quote

# Paleta del mockup
INK, INK_2, MUTED, MUTED_2 = "#17151C", "#3E3A45", "#5B5766", "#6B6577"
BG, CARD, LINE, LINE_2 = "#F4F3F7", "#FFFFFF", "#E6E3EC", "#D5D1DD"
PURPLE, PURPLE_SOFT, PURPLE_DEEP, LINK = "#A100FF", "#FBF7FF", "#460073", "#5A0091"
RED, RED_INK, RED_INK_2, RED_BG, RED_LINE = "#B3261E", "#8C1D18", "#6E1A16", "#FDECEC", "#F3C4C4"
AMBER, AMBER_INK, AMBER_INK_2, AMBER_BG, AMBER_DOT = "#8A5A00", "#6B4500", "#6B4500", "#FFF3DC", "#D48A00"
GREEN, GREEN_BG, GREY_DOT = "#2E7D4F", "#E6F4EC", "#C9C4D3"
NAV_BG, NAV_ACTIVE, NAV_TEXT, NAV_MUTED, NAV_LINE = "#17151C", "#2A2631", "#CFC9DA", "#A9A3B6", "#2E2A35"

# Iconos de la navegación (los del mockup), como imagen de fondo de cada botón
_NAV_ICONS = {
    "control": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/>'
               '<rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/><path d="M8 3v4"/>'
                '<path d="M16 3v4"/>',
    "suppliers": '<path d="M3 21h18"/><path d="M5 21V9l7-5 7 5v12"/><path d="M9 21v-6h6v6"/>',
    "simulator": '<path d="M4 19l5-6 4 3 7-9"/><circle cx="20" cy="7" r="1.5"/>',
    "transparency": '<circle cx="12" cy="12" r="9"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "settings": '<path d="M4 7h10"/><path d="M18 7h2"/><circle cx="16" cy="7" r="2"/><path d="M4 17h2"/>'
                '<path d="M10 17h10"/><circle cx="8" cy="17" r="2"/>',
}


def _icon_url(view: str, color: str) -> str:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_NAV_ICONS[view]}</svg>')
    return "data:image/svg+xml," + quote(svg)


def _nav_icons() -> str:
    """Icono de cada entrada del menú: gris claro y, en la activa (navon-), blanco."""
    return "".join(f'.st-key-nav-{v} a {{ background-image: url("{_icon_url(v, NAV_TEXT)}"); }}'
                   f'.st-key-navon-{v} a {{ background-image: url("{_icon_url(v, "#FFFFFF")}"); }}'
                   for v in _NAV_ICONS)


BASE_CSS = f"""
<style>
/* ---- Fuera el «cromo» de Streamlit: cabecera, menú, barra de herramientas y pie ---- */
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer,
[data-testid="stStatusWidget"], [data-testid="stSidebarCollapseButton"], [data-testid="stSidebarHeader"],
[data-testid="collapsedControl"], [data-testid="stExpandSidebarButton"] {{ display: none !important; }}
html, body, .stApp {{ background: {BG}; }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button {{
  font-family: 'IBM Plex Sans', system-ui, sans-serif; }}
.num {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
.block-container {{ padding: 32px 40px 48px !important; max-width: none !important; }}
.block-container [data-testid="stVerticalBlock"] {{ gap: 32px; }}
.stMarkdown p {{ margin: 0; }}
a {{ color: {LINK}; }} a:hover {{ color: #3D0063; }}

/* ---- Navegación lateral oscura (248 px, como el mockup) ---- */
section[data-testid="stSidebar"] {{ width: 248px !important; min-width: 248px !important; max-width: 248px !important;
  background: {NAV_BG}; }}
section[data-testid="stSidebar"] > div {{ padding: 0 !important; }}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 28px 20px !important; }}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: 4px; }}
.nav-brand {{ display: flex; align-items: center; gap: 12px; margin-bottom: 28px; }}
.nav-brand .t {{ font-weight: 700; font-size: 16px; letter-spacing: .2px; color: #FFFFFF; display: block; }}
.nav-brand .s {{ font-size: 12px; color: {NAV_MUTED}; display: block; }}
/* Menú: st.page_link reales (un enlace por página de st.navigation) */
section[data-testid="stSidebar"] :is([class*="st-key-nav-"], [class*="st-key-navon-"]) a {{ display: flex;
  justify-content: flex-start; align-items: center; gap: 12px; padding: 12px 14px 12px 44px; min-height: 46px;
  border: none; border-radius: 8px; background-color: transparent !important; background-repeat: no-repeat;
  background-position: 14px center; color: {NAV_TEXT} !important; text-decoration: none; box-shadow: none; }}
section[data-testid="stSidebar"] :is([class*="st-key-nav-"], [class*="st-key-navon-"]) a :is(p, span) {{
  color: inherit !important; font-size: 15px; font-weight: 400; text-align: left; }}
section[data-testid="stSidebar"] [class*="st-key-nav-"] a:hover {{ background-color: #221F28 !important;
  color: #FFFFFF !important; }}
section[data-testid="stSidebar"] [class*="st-key-navon-"] a {{ background-color: {NAV_ACTIVE} !important;
  color: #FFFFFF !important; box-shadow: inset 3px 0 0 {PURPLE}; }}
section[data-testid="stSidebar"] [class*="st-key-navon-"] a :is(p, span) {{ font-weight: 600; }}
:is([class*="st-key-nav-"], [class*="st-key-navon-"]) a:focus-visible {{ outline: 2px solid {PURPLE};
  outline-offset: 2px; }}
{_nav_icons()}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {{
  min-height: calc(100vh - 56px); }}
section[data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has(> .st-key-navdemo) {{ margin-top: auto; }}
.st-key-navdemo {{ padding: 0 4px 12px; }}
.st-key-navdemo label p {{ font-size: 13px !important; color: {NAV_MUTED} !important; }}
.nav-foot {{ display: flex; flex-direction: column; gap: 10px; font-size: 13px; color: {NAV_MUTED};
  border-top: 1px solid {NAV_LINE}; padding-top: 18px; }}
.nav-foot .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }}

/* ---- Tipografía y bloques del mockup ---- */
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{ padding: 0 !important; scroll-margin-top: 0; }}
.stMarkdown [data-testid="stHeaderActionElements"], .stMarkdown h1 a, .stMarkdown h2 a, .stMarkdown h3 a {{
  display: none !important; }}
.overline {{ font-size: 13px; font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase; color: {MUTED_2}; }}
.stMarkdown .h1, .h1 {{ margin: 0 !important; font-size: 30px !important; font-weight: 700; letter-spacing: -.3px; color: {INK}; line-height: 1.25; }}
.stMarkdown .h2, .h2 {{ margin: 0 !important; font-size: 19px !important; font-weight: 700; color: {INK};
  line-height: 1.3 !important; }}
.stMarkdown .h3, .h3 {{ margin: 0 !important; font-size: 13px !important; line-height: 1.4 !important; font-weight: 700; letter-spacing: .8px; text-transform: uppercase; color: {MUTED}; }}
.sub {{ font-size: 13px; color: {MUTED}; }}
.muted {{ color: {MUTED}; }}
.card {{ background: {CARD}; border-radius: 12px; border: 1px solid {LINE}; padding: 28px; display: flex;
  flex-direction: column; gap: 14px; box-sizing: border-box; }}
.card-head {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 12px; }}
.chip {{ display: inline-flex; align-self: flex-start; align-items: center; gap: 6px; font-size: 12px; font-weight: 700;
  padding: 4px 8px; border-radius: 999px; white-space: nowrap; }}
.chip.red {{ color: {RED_INK}; background: {RED_BG}; }}
.chip.amber {{ color: {AMBER_INK}; background: {AMBER_BG}; }}
.chip.green {{ color: {GREEN}; background: {GREEN_BG}; }}
.chip.grey {{ color: {MUTED}; background: {BG}; }}
.chip.purple {{ color: {PURPLE_DEEP}; background: #F1DDFF; }}

/* Banner de estado */
.banner {{ display: flex; align-items: center; gap: 14px; }}
.banner .t {{ font-weight: 700; font-size: 17px; display: block; }}
.banner .s {{ font-size: 14px; display: block; }}
[class*="st-key-banner-"] {{ border-radius: 12px; padding: 16px 20px; }}
.st-key-banner-red {{ background: {RED_BG}; border: 1px solid {RED_LINE}; }}
.st-key-banner-red .t {{ color: {RED_INK}; }} .st-key-banner-red .s {{ color: {RED_INK_2}; }}
.st-key-banner-ok {{ background: {GREEN_BG}; border: 1px solid #BFE3CC; }}
.st-key-banner-ok .t {{ color: #1D5A37; }} .st-key-banner-ok .s {{ color: #1D5A37; }}
[class*="st-key-banner-"] [data-testid="stHorizontalBlock"] {{ align-items: center; }}

/* KPIs */
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 24px; }}
.kpi {{ background: {CARD}; border-radius: 12px; padding: 24px; display: flex; flex-direction: column; gap: 12px;
  border: 1px solid {LINE}; }}
.kpi.alert {{ border-color: {RED_LINE}; box-shadow: 0 0 0 3px {RED_BG}; }}
.kpi .k {{ font-size: 13px; font-weight: 600; color: {MUTED}; text-transform: uppercase; letter-spacing: .8px; }}
.kpi .v {{ display: flex; align-items: baseline; gap: 6px; }}
.kpi .v .num {{ font-size: 40px; font-weight: 600; line-height: 1; }}
.kpi .v .u {{ font-size: 16px; color: {MUTED}; }}
.kpi .s {{ font-size: 14px; color: {MUTED}; }}

/* Paneles con widgets dentro (cola, detalle, mapa...) */
[class*="st-key-panel-"] {{ background: {CARD}; border-radius: 12px; border: 1px solid {LINE}; padding: 28px;
  box-sizing: border-box; }}
.st-key-panel-detail {{ padding: 26px; }}
.st-key-panel-queue [data-testid="stVerticalBlock"] {{ gap: 18px; }}
.st-key-panel-detail > div > [data-testid="stVerticalBlock"] {{ gap: 28px; }}

/* Tarjetas y filas clicables: HTML propio + st.button real e invisible encima (cola y ranking) */
:is([class*="st-key-qcard-"], [class*="st-key-rk-"]) {{ position: relative; }}
:is([class*="st-key-qbtn-"], [class*="st-key-rkbtn-"]) {{ position: absolute !important; inset: 0; z-index: 2;
  margin: 0 !important; }}
:is([class*="st-key-qbtn-"], [class*="st-key-rkbtn-"]) button {{ width: 100%; height: 100%; opacity: 0;
  cursor: pointer; }}
[class*="st-key-qcard-"]:has(button:focus-visible) :is(.qitem, .qrow) {{ outline: 2px solid {PURPLE};
  outline-offset: 2px; }}
[class*="st-key-qcard-"]:hover .qrow {{ border-color: #C9B3DD; }}
.qitem {{ display: flex; flex-direction: column; gap: 12px; padding: 20px; border-radius: 10px; background: {CARD};
  border: 1px solid {LINE}; color: {INK}; }}
[class*="st-key-qcard-"]:hover .qitem {{ border-color: #C9B3DD; }}
.qitem.sel {{ background: {PURPLE_SOFT}; border: 2px solid {PURPLE}; padding: 19px; }}
.qitem .top {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
.qitem .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.qitem.done {{ border-left: 4px solid {GREEN}; padding-left: 17px; }}
.qitem.off {{ opacity: .62; }}
.qitem.off .m {{ text-decoration: line-through; }}
.qitem .m {{ font-size: 22px; font-weight: 600; white-space: nowrap; }}
.qrows {{ display: flex; flex-direction: column; gap: 8px; }}
.st-key-panel-queue [data-testid="stExpander"] details {{ border: none; background: transparent; }}
.st-key-panel-queue [data-testid="stExpander"] summary {{ padding: 4px 0; font-size: 13px; font-weight: 700;
  letter-spacing: .8px; text-transform: uppercase; color: {MUTED}; }}
.qitem .m .e {{ font-size: 13px; font-family: 'IBM Plex Sans', sans-serif; font-weight: 500; color: {MUTED}; }}
.qitem .n {{ font-size: 16px; font-weight: 700; display: block; }}
.qitem .w {{ font-size: 14px; color: {MUTED}; display: block; }}
.qitem .a {{ font-size: 13px; color: {INK_2}; }}
.qrow {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 10px 12px;
  border-radius: 8px; border: 1px solid {LINE}; font-size: 14px; }}
.qrow .w {{ font-size: 13px; color: {MUTED}; }}

/* Detalle de la alerta */
.stMarkdown .det-name, .det-name {{ margin: 0 !important; font-size: 24px !important; line-height: 1.3 !important; font-weight: 700; color: {INK}; }}
.det-sub {{ font-size: 15px; color: {MUTED}; }}
/* Recurrencia de compra y pedido en tránsito (historial sintético) */
.buy {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; font-size: 14px; color: {MUTED}; }}
.buy .t {{ flex-basis: 100%; color: {INK_2}; }}
.buy .note {{ flex-basis: 100%; font-size: 12px; color: {MUTED}; font-style: italic; }}
.what {{ margin: 0; font-size: 17px; line-height: 1.5; color: {INK}; }}
.quote {{ margin: 0; padding: 12px 16px; background: {BG}; border-radius: 8px; font-size: 15px; color: {INK_2};
  font-style: italic; }}
.quote mark {{ background: #F1DDFF; color: inherit; padding: 0 2px; }}
.boxes {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }}
.box {{ padding: 14px; border-radius: 10px; background: {BG}; display: flex; flex-direction: column; gap: 4px; }}
.box .l {{ font-size: 13px; color: {MUTED}; }} .box .s {{ font-size: 13px; color: {MUTED}; }}
.box .v {{ font-size: 26px; font-weight: 600; }} .box .t {{ font-size: 18px; font-weight: 700; }}
.box.red {{ background: {RED_BG}; }} .box.red .l, .box.red .s {{ color: {RED_INK_2}; }} .box.red .v {{ color: {RED_INK}; }}
.box.amber {{ background: {AMBER_BG}; }} .box.amber .l, .box.amber .s {{ color: {AMBER_INK}; }}
.box.amber .v {{ color: {AMBER_INK}; }}
.box.green {{ background: {GREEN_BG}; }} .box.green .v {{ color: {GREEN}; }}
.steps {{ margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }}
.steps li {{ display: flex; gap: 14px; align-items: flex-start; padding: 12px 14px; border: 1px solid {LINE};
  border-radius: 10px; }}
.steps .i {{ flex: 0 0 26px; height: 26px; border-radius: 50%; background: {INK}; color: #FFFFFF; font-size: 13px;
  display: flex; align-items: center; justify-content: center; }}
.steps .b {{ flex: 1; display: flex; flex-direction: column; gap: 2px; }}
.steps .x {{ font-size: 15px; font-weight: 600; }} .steps .o {{ font-size: 13px; color: {MUTED}; }}
.trust {{ display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: {INK_2}; }}
.trust span {{ display: flex; align-items: center; gap: 8px; }}
.st-key-decision {{ border-top: 1px solid {LINE}; padding-top: 18px; }}
.st-key-decision [data-testid="stHorizontalBlock"] {{ align-items: center; gap: 10px; }}
.decided {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 8px;
  font-size: 14px; font-weight: 600; }}
.decided.ok {{ background: {GREEN_BG}; color: #1D5A37; }}
.decided.fa {{ background: {BG}; color: {INK_2}; }}
.decided .w {{ font-weight: 400; color: {MUTED}; }}
/* «Ver noticia original»: un st.popover con aspecto de enlace */
[class*="st-key-news-"] button {{ border: none !important; background: transparent !important; padding: 2px 0 !important;
  min-height: 0 !important; color: {LINK} !important; box-shadow: none !important; }}
[class*="st-key-news-"] button p {{ font-size: 14px; font-weight: 600; color: {LINK}; }}
[class*="st-key-news-"] button:hover p {{ text-decoration: underline; }}
.news-body {{ display: flex; flex-direction: column; gap: 8px; max-width: 560px; font-size: 14px; color: {INK_2}; }}
.news-body .hl {{ font-size: 16px; font-weight: 700; color: {INK}; }}

/* Botones (mockup: 44 px de alto, radio 8, primario morado, secundario blanco con borde) */
.stButton button, .stFormSubmitButton button {{ font-family: inherit; font-size: 15px; font-weight: 600;
  padding: 12px 18px; min-height: 44px; border-radius: 8px; white-space: nowrap; }}
.stButton button p, .stFormSubmitButton button p {{ font-size: 15px; font-weight: 600; white-space: nowrap; }}
.stamp {{ font-size: 14px; color: {MUTED}; text-align: right; padding-bottom: 12px; }}
.stButton button[kind="secondary"], .stFormSubmitButton button[kind="secondary"] {{ border: 1px solid {LINE_2};
  background: #FFFFFF; color: {INK}; }}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{ border: none; background: {PURPLE};
  color: #FFFFFF; }}
.stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover {{ background: #8A00DB; }}
.st-key-review-now button {{ background: {RED} !important; }}
.st-key-review-now button:hover {{ background: #951F18 !important; }}
/* «Simular escenario»: st.page_link con aspecto de botón secundario */
.st-key-go-sim a {{ display: flex; justify-content: center; align-items: center; min-height: 44px; padding: 0 18px;
  border: 1px solid {LINE_2}; border-radius: 8px; background: #FFFFFF; color: {INK} !important;
  text-decoration: none; }}
.st-key-go-sim a:hover {{ border-color: {PURPLE}; background: {PURPLE_SOFT}; }}
.st-key-go-sim a :is(p, span) {{ font-size: 15px; font-weight: 600; color: inherit !important; white-space: nowrap; }}

/* Calendario de roturas: una fila por medicamento sobre los próximos 90 días */
.cal {{ display: grid; grid-template-columns: 210px minmax(0, 1fr) 150px; column-gap: 18px; row-gap: 16px;
  align-items: center; margin-top: 18px; }}
.cal.small {{ grid-template-columns: 150px minmax(0, 1fr) 118px; column-gap: 14px; }}
.cal .lbl {{ min-width: 0; }}
.cal .lbl strong {{ display: block; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.cal .lbl .w {{ display: block; font-size: 13px; color: {MUTED}; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }}
.cal .track {{ position: relative; height: 24px; background: {BG}; border-radius: 4px; }}
.cal .seg {{ position: absolute; top: 4px; bottom: 4px; }}
.cal .seg.ok {{ background: {GREEN}; }}
.cal .seg.out {{ background: {RED}; }}
.cal .seg.out.est {{ background: repeating-linear-gradient(135deg, {RED} 0 5px, #EBA9A4 5px 9px); }}
.cal .seg.back {{ background: #BFE3CC; }}
.cal .seg.back.est {{ background: repeating-linear-gradient(135deg, #BFE3CC 0 5px, #EEF8F2 5px 9px); }}
.cal .mk {{ position: absolute; top: 50%; z-index: 2; }}
.cal .mk.rec {{ width: 11px; height: 11px; background: {INK}; border: 2px solid #FFFFFF;
  transform: translate(-50%, -50%) rotate(45deg); }}
.cal .mk.rec.est {{ background: #FFFFFF; border: 2px solid {INK}; }}
.cal .mk.alt {{ width: 0; height: 0; border-left: 7px solid transparent; border-right: 7px solid transparent;
  border-bottom: 12px solid {PURPLE}; transform: translate(-50%, -50%); }}
.cal .more {{ position: absolute; right: 4px; top: 50%; transform: translateY(-50%); font-size: 12px; font-weight: 700;
  color: #FFFFFF; z-index: 2; }}
.cal .today {{ position: relative; align-self: stretch; pointer-events: none; z-index: 3; }}
.cal .today::before {{ content: ""; position: absolute; top: -6px; bottom: 20px; left: var(--x); width: 2px;
  background: {PURPLE}; }}
.cal .today span {{ position: absolute; top: -24px; left: var(--x); transform: translateX(-50%); font-size: 12px;
  font-weight: 700; color: {PURPLE_DEEP}; }}
.cal .axis {{ position: relative; height: 16px; font-size: 12px; color: {MUTED_2}; }}
.cal .axis span {{ position: absolute; transform: translateX(-50%); white-space: nowrap; }}
.cal .val {{ display: flex; flex-direction: column; align-items: flex-end; text-align: right; }}
.cal .val .num {{ font-size: 16px; font-weight: 600; }}
.cal .val .st {{ font-size: 12px; font-weight: 700; letter-spacing: .3px; }}
.legend .sw.hatch {{ background: repeating-linear-gradient(135deg, {RED} 0 3px, #EBA9A4 3px 6px); }}
.legend .mk-rec {{ width: 9px; height: 9px; background: {INK}; transform: rotate(45deg); }}
.legend .mk-alt {{ width: 0; height: 0; border-left: 6px solid transparent; border-right: 6px solid transparent;
  border-bottom: 10px solid {PURPLE}; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: {MUTED}; }}
.legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
.legend .sw {{ width: 14px; height: 10px; border-radius: 2px; }}
.legend .dot {{ width: 10px; height: 10px; border-radius: 50%; }}

/* Tablas HTML (proveedores, simulador, transparencia) */
.tbl {{ width: 100%; border-collapse: collapse; font-size: 14px; margin: 0 !important; border: none !important; }}
.stMarkdown .tbl th, .stMarkdown .tbl td {{ border: none !important; border-bottom: 1px solid {LINE} !important;
  background: transparent !important; }}
.stMarkdown .tbl tr:last-child td {{ border-bottom: none !important; }}
.stMarkdown .tbl tr {{ background: transparent !important; }}
.kpi .v .txt {{ font-size: 30px; font-weight: 700; line-height: 1.1; }}
.tbl th {{ text-align: left; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .6px;
  color: {MUTED}; padding: 8px 10px; border-bottom: 1px solid {LINE}; }}
.tbl td {{ padding: 10px; border-bottom: 1px solid {LINE}; vertical-align: top; color: {INK}; }}
.tbl tr:last-child td {{ border-bottom: none; }}
.tbl td.r, .tbl th.r {{ text-align: right; }}
.tbl .num, .tbl td.r {{ white-space: nowrap; }}      /* «10,2 M€» o «16 %» nunca en dos líneas */
.tbl .w {{ display: block; font-size: 13px; color: {MUTED}; }}
.tbl-wrap {{ overflow-x: auto; }}
.bar {{ height: 8px; border-radius: 4px; background: {PURPLE}; }}
/* Ranking de vulnerabilidad: filas clicables que abren la ficha */
.st-key-panel-ranking [data-testid="stVerticalBlock"] {{ gap: 0; }}
.st-key-panel-ranking .card-head {{ margin-bottom: 12px; }}
.rk {{ display: grid; grid-template-columns: 26px minmax(0, 3fr) 90px 170px 14px;
  gap: 16px; align-items: center; padding: 14px 10px; border-bottom: 1px solid {LINE}; font-size: 14px; color: {INK};
  border-radius: 6px; }}
.rk.head {{ font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .6px; color: {MUTED};
  padding: 8px 10px; border-radius: 0; }}
.rk .w {{ display: block; font-size: 13px; color: {MUTED}; }}
.rk .r {{ text-align: right; }}
.tip {{ display: inline-block; margin-left: 8px; font-size: 14px; font-weight: 400; color: {MUTED_2}; cursor: help;
  text-transform: none; letter-spacing: 0; vertical-align: baseline; }}
.tip:hover, .tip:focus-visible {{ color: {PURPLE}; outline: none; }}
.sheet-chips {{ display: flex; gap: 8px; flex-wrap: wrap; }}
/* Ajustes: tarjetas con filas de «etiqueta · valor» */
[class*="st-key-panel-set-"] [data-testid="stVerticalBlock"] {{ gap: 20px; }}
.srow {{ display: flex; justify-content: space-between; gap: 16px; padding: 4px 0; font-size: 15px; }}
.srow .l {{ color: {MUTED}; }} .srow .v {{ font-weight: 600; text-align: right; }}
.settings-grid {{ max-width: 860px; }}
.rk .go {{ color: {MUTED}; font-size: 18px; line-height: 1; }}
[class*="st-key-rk-"]:hover .rk {{ background: {PURPLE_SOFT}; }}
[class*="st-key-rk-"]:hover .rk .go {{ color: {PURPLE}; }}
[class*="st-key-rk-"]:has(button:focus-visible) .rk {{ outline: 2px solid {PURPLE}; outline-offset: -2px; }}
.bar-bg {{ background: {BG}; border-radius: 4px; width: 100%; }}

/* Avisos (st.toast) abajo a la derecha: arriba tapaban la X de la ventana que se abre justo después */
[data-testid="stToastContainer"] {{ top: auto !important; bottom: 24px !important; }}

/* Modo demo: barra, ventana paso a paso y alerta recién llegada */
.st-key-demo-bar {{ background: {PURPLE_SOFT}; border: 1px dashed #C9A2EE; border-radius: 12px; padding: 12px 16px; }}
.demo-t {{ font-size: 14px; color: {PURPLE_DEEP}; }}
.demo-t b {{ letter-spacing: 1px; }}
.dsteps {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }}
.ds {{ display: flex; gap: 14px; align-items: flex-start; padding: 14px 16px; border-radius: 10px;
  border: 1px solid {LINE}; background: {CARD}; transition: opacity .3s; }}
.ds.todo {{ opacity: .38; }}
.ds.now {{ border: 2px solid {PURPLE}; background: {PURPLE_SOFT}; padding: 13px 15px; }}
.ds .dn {{ flex: 0 0 30px; height: 30px; border-radius: 50%; background: {LINE}; color: {INK}; font-weight: 700;
  display: flex; align-items: center; justify-content: center; }}
.ds.done .dn {{ background: {GREEN}; color: #FFFFFF; }}
.ds.now .dn {{ background: {PURPLE}; color: #FFFFFF; animation: dpulse 1s ease-in-out infinite; }}
.ds .db {{ display: flex; flex-direction: column; gap: 6px; min-width: 0; }}
.ds .dt {{ font-size: 13px; font-weight: 700; letter-spacing: .8px; text-transform: uppercase; color: {MUTED}; }}
.ds .hl {{ font-size: 17px; font-weight: 700; color: {INK}; }}
.ds .sm {{ font-size: 15px; color: {INK_2}; line-height: 1.45; }}
.ds .how {{ font-size: 13px; color: {MUTED}; }}
.ds .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.ds .chips .chip {{ white-space: normal; }}
@keyframes dpulse {{ 50% {{ box-shadow: 0 0 0 6px rgba(161, 0, 255, .18); }} }}
.qitem.new {{ animation: qnew 1.4s ease-in-out 4; }}
@keyframes qnew {{ 50% {{ box-shadow: 0 0 0 6px rgba(161, 0, 255, .22); }} }}

/* Calendario: el supuesto de la proyección y el semáforo de medicamentos */
.assume {{ margin: 0 !important; font-size: 15px; color: {INK_2}; }}
.sem .g b.muted {{ color: {MUTED}; font-weight: 500; }}
.st-key-panel-semaforo [data-testid="stVerticalBlock"] {{ gap: 10px; }}
.sem {{ display: flex; flex-direction: column; gap: 6px; padding: 12px 14px; border-radius: 10px;
  border: 1px solid {LINE}; border-left: 5px solid {GREEN}; }}
.sem.peligro {{ border-left-color: {AMBER_DOT}; }}
.sem.rotura {{ border-left-color: {RED}; }}
.sem .top {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
.sem .n {{ font-size: 15px; font-weight: 700; }}
.sem .g {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; font-size: 14px; }}
.sem .g > span {{ display: flex; flex-direction: column; }}
.sem .g .l {{ font-size: 12px; color: {MUTED}; }}
.sem .g b {{ color: {INK}; font-weight: 600; }}
.sem .w {{ font-size: 12px; color: {MUTED}; font-weight: 400; }}
.sem .w.late {{ color: {RED_INK}; font-weight: 600; }}
.sem > .w {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
[class*="st-key-sem-"]:not([class*="st-key-sem-order-"]) {{ gap: 6px !important; }}
[class*="st-key-sem-order-"] {{ align-self: flex-end; margin-top: 10px !important; }}
.st-key-panel-semaforo {{ overflow-y: auto; }}
[class*="st-key-sem-order-"] button {{ min-height: 34px !important; padding: 4px 14px !important; }}
[class*="st-key-sem-order-"] button p {{ font-size: 14px !important; }}
.st-key-cal-act, .st-key-cal-act [data-testid="stVerticalBlock"] {{ gap: 14px !important; }}

/* Ventanas modales (st.dialog): centradas, con el fondo difuminado */
[data-testid="stDialog"] {{ backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
  background: rgba(23, 21, 28, .38) !important; }}
[data-testid="stDialog"] [role="dialog"] {{ background: {CARD}; border-radius: 14px; }}
.st-key-dlg-info, .st-key-dlg-info [data-testid="stVerticalBlock"] {{ gap: 24px !important; }}
.st-key-dlg-act {{ background: {BG}; border-radius: 12px; padding: 18px; }}
.st-key-dlg-act, .st-key-dlg-act [data-testid="stVerticalBlock"] {{ gap: 16px !important; }}
.news-card {{ padding: 14px 16px; border-radius: 10px; border: 1px solid {LINE}; }}
.news-card .news-body {{ max-width: none; }}
.calc {{ margin: 0; padding: 10px 12px; border-radius: 8px; background: {PURPLE_SOFT}; border: 1px solid #EBD9FA;
  font-size: 13px; color: {INK_2}; }}

/* Falsa alarma (popover con el motivo) y «Crear pedido o recordatorio» */
[class*="fapop-"] button {{ min-height: 44px; border-radius: 8px; border: 1px solid {LINE_2}; background: #FFFFFF; }}
[class*="fapop-"] button p {{ font-size: 15px; font-weight: 600; }}
[class*="st-key-more-"] button {{ min-height: 0 !important; padding: 4px 0 !important; color: {LINK} !important; }}
[class*="st-key-more-"] button p {{ font-size: 14px; color: {LINK}; }}
[class*="st-key-more-"] button:hover p {{ text-decoration: underline; }}

/* Acciones en curso (pedidos y recordatorios) y su resumen en cada tarjeta */
.qitem .acts {{ align-self: flex-start; font-size: 13px; font-weight: 600; color: {PURPLE_DEEP}; background: #F1DDFF;
  padding: 4px 8px; border-radius: 6px; }}
.st-key-panel-actions [data-testid="stVerticalBlock"] {{ gap: 10px; }}
[class*="st-key-act-"] {{ border-top: 1px solid {LINE}; padding-top: 10px; }}
.act {{ display: flex; gap: 10px; align-items: flex-start; font-size: 14px; color: {INK}; padding: 4px 0; }}
.act .ic {{ font-size: 18px; line-height: 1.2; }}
.act .w {{ display: block; font-size: 13px; color: {MUTED}; }}
[class*="st-key-done-"] button {{ min-height: 36px; padding: 6px 12px; }}

/* Proveedores: filas de tarjetas de la misma altura, sin huecos */
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 24px; align-items: stretch; }}
.grid2 > .card {{ height: 100%; }}
.rk.lst {{ grid-template-columns: minmax(0, 2fr) minmax(0, 1.4fr) 80px 14px; }}

/* Formularios y entradas con el estilo de las tarjetas */
[data-testid="stForm"] {{ background: transparent; border: none; padding: 0; }}
[data-testid="stExpander"] details {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}
.stTextArea textarea, .stTextInput input {{ font-size: 15px; }}
.foot {{ font-size: 13px; color: {MUTED_2}; }}
</style>
"""


RADAR_LOGO = ('<svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true" fill="none" stroke="#A100FF" '
              'stroke-width="2"><circle cx="16" cy="16" r="13"></circle><circle cx="16" cy="16" r="7"></circle>'
              '<path d="M16 16 L26 8" stroke-linecap="round"></path><circle cx="16" cy="16" r="2" fill="#A100FF">'
              '</circle></svg>')
ICON_ALERT = (f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{RED}" stroke-width="2.2" '
              'aria-hidden="true"><path d="M12 3l10 18H2z"></path><path d="M12 10v5"></path><path d="M12 18h.01">'
              '</path></svg>')
ICON_OK_BIG = (f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{GREEN}" stroke-width="2.2" '
               'aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M8 12l3 3 5-6"></path></svg>')
ICON_CHECK = (f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{GREEN}" stroke-width="2.5" '
              'aria-hidden="true"><path d="M5 12l5 5L20 7"></path></svg>')
ICON_WARN = (f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{AMBER_DOT}" stroke-width="2.5" '
             'aria-hidden="true"><path d="M12 4l9 16H3z"></path><path d="M12 10v4"></path><path d="M12 17h.01"></path>'
             '</svg>')
