"""Estilo del panel, copiado de docs/mockup_centro_control.html (colores, tipografía, radios y espaciados).

Las fuentes IBM Plex se sirven desde static/fonts (ver .streamlit/config.toml): sin Google Fonts.
Los widgets de Streamlit que hacen falta (navegación, botones, formularios) se visten con su clase
`st-key-<key>`, que Streamlit añade a cada elemento con `key`.
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
    "suppliers": '<path d="M3 21h18"/><path d="M5 21V9l7-5 7 5v12"/><path d="M9 21v-6h6v6"/>',
    "simulator": '<path d="M4 19l5-6 4 3 7-9"/><circle cx="20" cy="7" r="1.5"/>',
    "transparency": '<circle cx="12" cy="12" r="9"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
}


def _icon_url(view: str, color: str) -> str:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_NAV_ICONS[view]}</svg>')
    return "data:image/svg+xml," + quote(svg)


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
.block-container [data-testid="stVerticalBlock"] {{ gap: 24px; }}
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
section[data-testid="stSidebar"] [class*="st-key-nav-"] button {{ width: 100%; justify-content: flex-start;
  gap: 12px; padding: 12px 14px 12px 44px; min-height: 46px; border: none !important; border-radius: 8px;
  background-color: transparent; background-repeat: no-repeat; background-position: 14px center;
  color: {NAV_TEXT} !important; font-size: 15px; font-weight: 400; box-shadow: none; }}
section[data-testid="stSidebar"] [class*="st-key-nav-"] button > div {{ justify-content: flex-start; width: 100%; }}
section[data-testid="stSidebar"] [class*="st-key-nav-"] button p {{ text-align: left; color: inherit; }}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {{
  min-height: calc(100vh - 56px); }}
section[data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has(> .st-key-navfoot) {{ margin-top: auto; }}
section[data-testid="stSidebar"] [class*="st-key-nav-"] button:hover {{ background-color: #221F28;
  color: #FFFFFF !important; }}
[class*="st-key-nav-"] button:focus-visible {{ outline: 2px solid {PURPLE}; outline-offset: 2px; }}
[class*="st-key-nav-"] button p {{ font-size: 15px; }}
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
.card {{ background: {CARD}; border-radius: 12px; border: 1px solid {LINE}; padding: 22px; display: flex;
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
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; }}
.kpi {{ background: {CARD}; border-radius: 12px; padding: 20px; display: flex; flex-direction: column; gap: 8px;
  border: 1px solid {LINE}; }}
.kpi.alert {{ border-color: {RED_LINE}; box-shadow: 0 0 0 3px {RED_BG}; }}
.kpi .k {{ font-size: 13px; font-weight: 600; color: {MUTED}; text-transform: uppercase; letter-spacing: .8px; }}
.kpi .v {{ display: flex; align-items: baseline; gap: 6px; }}
.kpi .v .num {{ font-size: 40px; font-weight: 600; line-height: 1; }}
.kpi .v .u {{ font-size: 16px; color: {MUTED}; }}
.kpi .s {{ font-size: 14px; color: {MUTED}; }}

/* Paneles con widgets dentro (cola, detalle, mapa...) */
[class*="st-key-panel-"] {{ background: {CARD}; border-radius: 12px; border: 1px solid {LINE}; padding: 22px;
  box-sizing: border-box; }}
.st-key-panel-detail {{ padding: 26px; }}
.st-key-panel-queue [data-testid="stVerticalBlock"] {{ gap: 14px; }}
.st-key-panel-detail > div > [data-testid="stVerticalBlock"] {{ gap: 22px; }}

/* Cola «Requiere tu decisión»: tarjeta HTML + botón invisible encima (toda la tarjeta es clicable) */
[class*="st-key-qcard-"] {{ position: relative; }}
[class*="st-key-qbtn-"] {{ position: absolute !important; inset: 0; z-index: 2; margin: 0 !important; }}
[class*="st-key-qbtn-"] button {{ width: 100%; height: 100%; opacity: 0; cursor: pointer; }}
[class*="st-key-qcard-"]:has(button:focus-visible) .qitem {{ outline: 2px solid {PURPLE}; outline-offset: 2px; }}
.qitem {{ display: flex; flex-direction: column; gap: 10px; padding: 16px; border-radius: 10px; background: {CARD};
  border: 1px solid {LINE}; color: {INK}; }}
[class*="st-key-qcard-"]:hover .qitem {{ border-color: #C9B3DD; }}
.qitem.sel {{ background: {PURPLE_SOFT}; border: 2px solid {PURPLE}; padding: 15px; }}
.qitem .top {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
.qitem .m {{ font-size: 22px; font-weight: 600; }}
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
details.news summary {{ cursor: pointer; color: {LINK}; font-size: 14px; font-weight: 600; list-style: none; }}
details.news summary::-webkit-details-marker {{ display: none; }}
details.news[open] .body {{ margin-top: 10px; padding: 12px 14px; border-radius: 8px; background: {BG}; font-size: 14px;
  color: {INK_2}; max-width: 520px; }}

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

/* ¿Cuánto aguantamos? */
.hold {{ display: flex; flex-direction: column; gap: 16px; }}
.hold .row {{ display: grid; grid-template-columns: 170px minmax(0, 1fr) 84px; gap: 14px; align-items: center; }}
.hold .lbl {{ font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.hold .bars {{ display: flex; flex-direction: column; gap: 4px; }}
.hold .stock {{ height: 12px; background: {INK_2}; border-radius: 3px; }}
.hold .rec {{ height: 12px; border: 2px dashed {RED}; border-radius: 3px; box-sizing: border-box; }}
.hold .v {{ font-size: 16px; font-weight: 600; text-align: right; }}
.hold .axis {{ display: flex; justify-content: space-between; font-size: 12px; color: {MUTED_2};
  border-top: 1px solid {LINE}; padding-top: 6px; }}
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
.tbl .w {{ display: block; font-size: 13px; color: {MUTED}; }}
.tbl-wrap {{ overflow-x: auto; }}
.bar {{ height: 8px; border-radius: 4px; background: {PURPLE}; }}
.bar-bg {{ background: {BG}; border-radius: 4px; width: 100%; }}

/* Formularios y entradas con el estilo de las tarjetas */
[data-testid="stForm"] {{ background: transparent; border: none; padding: 0; }}
[data-testid="stExpander"] details {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}
.stTextArea textarea, .stTextInput input {{ font-size: 15px; }}
.foot {{ font-size: 13px; color: {MUTED_2}; }}
</style>
"""


def nav_css(active: str) -> str:
    """Icono de cada entrada de la navegación y marca de la activa (fondo y filete morado a la izquierda)."""
    rules = []
    for view in _NAV_ICONS:
        on = view == active
        rules.append(f'.st-key-nav-{view} button {{ background-image: url("{_icon_url(view, "#FFFFFF" if on else NAV_TEXT)}"); }}')
        if on:
            rules.append(f".st-key-nav-{view} button {{ background-color: {NAV_ACTIVE} !important; color: #FFFFFF !important;"
                         f" font-weight: 600; box-shadow: inset 3px 0 0 {PURPLE} !important; }}"
                         f".st-key-nav-{view} button p {{ font-weight: 600; }}")
    return "<style>" + "".join(rules) + "</style>"


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
