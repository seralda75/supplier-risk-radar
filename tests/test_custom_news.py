"""Noticias cargadas por el usuario: validación del fichero, procesado con el pipeline y fuente del panel.
Nunca tocan data/results (la entrega): el conftest las redirige a una carpeta temporal."""
import hashlib
import io

import pandas as pd
import pytest

from core import custom_news, results, settings

COLS = custom_news.REQUIRED


def xlsx(rows, cols=COLS) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=cols).to_excel(buf, index=False)
    return buf.getvalue()


ROWS = [["X001", "2026-10-20", "Reuters", "Fire at Taizhou chemical park forces evacuation of several API plants",
         "A fire broke out at a chemical park in Taizhou."],
        ["X002", "2026-10-21", "BBC", "Central bank holds interest rates steady", "No change."]]


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else ""


def test_lee_xlsx_y_csv():
    assert [n["News_ID"] for n in custom_news.read(xlsx(ROWS), "n.xlsx")] == ["X001", "X002"]
    csv = pd.DataFrame(ROWS, columns=COLS).to_csv(index=False).encode("utf-8")
    news = custom_news.read(csv, "n.csv")
    assert news[0]["Published_Date"] == "2026-10-20" and news[1]["Source"] == "BBC"


def test_valida_las_columnas_y_los_datos():
    with pytest.raises(custom_news.NewsFileError, match="Faltan columnas: Summary"):
        custom_news.read(xlsx([r[:4] for r in ROWS], COLS[:4]), "n.xlsx")
    with pytest.raises(custom_news.NewsFileError, match="repetido"):
        custom_news.read(xlsx(ROWS + [ROWS[0]]), "n.xlsx")
    with pytest.raises(custom_news.NewsFileError, match="fecha"):
        custom_news.read(xlsx([["X1", "no-es-fecha", "s", "h", "x"]]), "n.xlsx")
    with pytest.raises(custom_news.NewsFileError, match="Headline"):
        custom_news.read(xlsx([["X1", "2026-10-20", "s", "", "x"]]), "n.xlsx")
    with pytest.raises(custom_news.NewsFileError, match="Formato"):
        custom_news.read(b"x", "n.txt")


def test_procesa_con_el_pipeline_y_no_toca_la_entrega():
    entrega = [results.path(s) for s in results.SPLITS]
    antes = [md5(p) for p in entrega]
    news = custom_news.read(xlsx(ROWS), "n.xlsx")
    pasos = []
    info = custom_news.process(news, name="n.xlsx", progress=lambda d, t, h: pasos.append((d, t)), use_llm=False)
    assert info["news"] == 2 and info["name"] == "n.xlsx" and info["mode"] == "reglas"
    assert pasos[0] == (0, 2) and pasos[-1] == (2, 2)                     # la barra de progreso avanza
    d = results.load(results.CUSTOM)
    assert [r["news_id"] for r in d["results"]] == ["X001", "X002"]
    assert d["results"][0]["is_risk"] and "S003" in d["results"][0]["affected_ids"]
    assert not d["results"][1]["is_risk"]
    assert results.path(results.CUSTOM).parent != results.RESULTS_DIR
    assert [md5(p) for p in entrega] == antes                              # data/results, intacto


def test_la_fuente_por_defecto_son_las_noticias_del_dia_y_se_puede_volver():
    assert not custom_news.active()
    news = custom_news.read(xlsx(ROWS), "n.xlsx")
    custom_news.process(news, name="n.xlsx", use_llm=False)
    assert not custom_news.active()                       # cargar no cambia la fuente hasta activarla
    custom_news.use(True)
    assert custom_news.active() and settings.get("source") == "custom"
    custom_news.use(False)
    assert not custom_news.active() and custom_news.info()["news"] == 2    # lo cargado se conserva
    custom_news.use(True)
    custom_news.clear()
    assert not custom_news.active() and custom_news.info() is None
