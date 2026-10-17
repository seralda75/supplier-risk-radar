"""Comprueba que todo está listo. Ejecútalo en casa ANTES de salir y al llegar al evento.

Uso:  python scripts/check_env.py
"""
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OK, KO, WARN = "\033[92m✔\033[0m", "\033[91m✘\033[0m", "\033[93m!\033[0m"
problems = 0


def check(label, ok, hint="", optional=False):
    global problems
    if ok:
        print(f"  {OK} {label}")
    else:
        print(f"  {WARN if optional else KO} {label}" + (f"  → {hint}" if hint else ""))
        problems += 0 if optional else 1


print("\nPython")
check(f"Python {sys.version.split()[0]}", sys.version_info[:2] == (3, 12), "usa Python 3.12 (py -3.12 -m venv .venv)")

print("\nLibrerías")
for mod, pip in [("pandas", "pandas"), ("openpyxl", "openpyxl"), ("pydantic", "pydantic"),
                 ("requests", "requests"), ("chromadb", "chromadb"), ("rapidfuzz", "rapidfuzz"),
                 ("streamlit", "streamlit"), ("plotly", "plotly"), ("pytest", "pytest"),
                 ("dotenv", "python-dotenv")]:
    try:
        importlib.import_module(mod)
        check(mod, True)
    except ImportError:
        check(mod, False, f"pip install {pip}", optional=mod == "dotenv")

print("\nDatos del reto")
try:
    from core.config import TEST_XLSX, TRAIN_XLSX, VALIDATION_XLSX
    for label, p in [("entrenamiento", TRAIN_XLSX), ("validación", VALIDATION_XLSX), ("test", TEST_XLSX)]:
        check(f"{label}: {p.name}", p.exists())
except FileNotFoundError as e:
    check("Excel del reto en data/raw/", False, str(e))

print("\nHerramientas")
for tool, hint, opt in [("git", "instala git", False), ("ollama", "https://ollama.com/download", False),
                        ("node", "instala Node 20+ para n8n", True), ("docker", "opcional", True)]:
    check(tool, shutil.which(tool) is not None, hint, optional=opt)

print("\nOllama")
from core import llm  # noqa: E402
from core.config import EMBED_MODEL, LLM_FAST_MODEL, LLM_MODEL  # noqa: E402

up = llm.is_up()
check("servidor Ollama respondiendo", up, "ejecuta: ollama serve")
if up:
    models = llm.installed_models()
    for m, opt in [(LLM_MODEL, False), (EMBED_MODEL, False), (LLM_FAST_MODEL, True)]:
        found = any(x == m or x.startswith(m + ":") for x in models)
        check(f"modelo {m}", found, f"ollama pull {m}", optional=opt)
    try:
        out = llm.chat("Responde solo: OK", temperature=0)
        check(f"generación de texto ({out.strip()[:20]})", True)
    except Exception as e:  # noqa: BLE001
        check("generación de texto", False, str(e)[:80])
    try:
        check("embeddings", len(llm.embed(["hola"])[0]) > 0)
    except Exception as e:  # noqa: BLE001
        check("embeddings", False, str(e)[:80])

print("\nGPU (acelera mucho Ollama)")
gpu = shutil.which("nvidia-smi") and subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
check("GPU NVIDIA", bool(gpu), "sin GPU usa modelos pequeños: llama3.2:3b", optional=True)

print("\n" + ("✅ Todo listo" if problems == 0 else f"❌ {problems} problema(s) por resolver") + "\n")
sys.exit(1 if problems else 0)
