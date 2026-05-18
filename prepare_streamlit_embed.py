"""
prepare_streamlit_embed.py
══════════════════════════════════════════════════════════════════════════════
Cria dist/dashboard-env/ — Python portátil + Streamlit + deps.

Chamado pelo build_installer.bat durante o build. Requer internet
APENAS na máquina de build; o usuário final não precisa de nada.

Uso:
    python prepare_streamlit_embed.py [--python 3.11.9] [--force]

Resultado:
    dist/dashboard-env/          ← Python embutido pronto
    dist/_embed_cache/           ← cache de downloads (reutilizado em builds futuros)
══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# ── Configurações ─────────────────────────────────────────────────────────────
DEFAULT_PYTHON = "3.11.9"
ARCH           = "amd64"

PACKAGES = [
    "streamlit>=1.35",
    "plotly>=5.20",
    "pandas>=2.2",
    "watchdog>=4.0",
    "pyarrow",        # dependência silenciosa do pandas+streamlit
]

BASE_DIR   = Path(__file__).parent
DIST_DIR   = BASE_DIR / "dist"
OUTPUT_DIR = DIST_DIR / "dashboard-env"
CACHE_DIR  = DIST_DIR / "_embed_cache"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar(count: int, block: int, total: int) -> None:
    if total > 0:
        pct = min(count * block / total * 100, 100)
        filled = int(pct / 5)
        bar = "#" * filled + "." * (20 - filled)
        print(f"\r     [{bar}] {pct:5.1f}%", end="", flush=True)


def _download(url: str, dest: Path) -> None:
    print(f"  ↓  {url}")
    urllib.request.urlretrieve(url, dest, reporthook=_bar)
    print()


def _size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024


# ── Etapas ────────────────────────────────────────────────────────────────────

def step_download(python_ver: str) -> Path:
    """Baixa o Python embeddable (ou usa cache)."""
    embed_url = (
        f"https://www.python.org/ftp/python/{python_ver}/"
        f"python-{python_ver}-embed-{ARCH}.zip"
    )
    short = f"python-{python_ver}-embed-{ARCH}.zip"
    cached = CACHE_DIR / short

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if cached.exists():
        print(f"  [cache] {cached.name}")
    else:
        _download(embed_url, cached)

    return cached


def step_extract(zip_path: Path, force: bool) -> None:
    """Extrai o Python embutido para OUTPUT_DIR."""
    if OUTPUT_DIR.exists():
        if force:
            print(f"  Removendo {OUTPUT_DIR.name} anterior...")
            shutil.rmtree(OUTPUT_DIR)
        else:
            print(f"  {OUTPUT_DIR.name} ja existe (use --force para recriar)")
            return

    print(f"  Extraindo para {OUTPUT_DIR}...")
    OUTPUT_DIR.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(OUTPUT_DIR)
    print(f"  Extraido: {_size_mb(OUTPUT_DIR):.0f} MB")


def step_enable_site_packages() -> None:
    """Habilita site-packages no ._pth para que pip funcione."""
    pth_files = list(OUTPUT_DIR.glob("python*._pth"))
    if not pth_files:
        print("  [AVISO] Arquivo ._pth nao encontrado")
        return
    for pth in pth_files:
        content = pth.read_text(encoding="utf-8")
        if "import site" in content and "#import site" not in content:
            print(f"  site-packages ja habilitado ({pth.name})")
            return
        content = content.replace("#import site", "import site")
        pth.write_text(content, encoding="utf-8")
        print(f"  site-packages habilitado ({pth.name})")


def step_install_pip() -> Path:
    """Instala pip no Python embutido."""
    python_exe = OUTPUT_DIR / "python.exe"
    get_pip    = CACHE_DIR  / "get-pip.py"

    result = subprocess.run(
        [str(python_exe), "-m", "pip", "--version"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  pip ja instalado ({result.stdout.strip().split()[1]})")
        return python_exe

    if not get_pip.exists():
        _download("https://bootstrap.pypa.io/get-pip.py", get_pip)

    print("  Instalando pip...")
    subprocess.run([str(python_exe), str(get_pip), "--quiet"], check=True)
    print("  pip instalado")
    return python_exe


def step_install_packages(python_exe: Path) -> None:
    """Instala Streamlit e dependências no Python embutido."""
    print("  Instalando pacotes:")
    for pkg in PACKAGES:
        print(f"    - {pkg}")

    subprocess.run(
        [str(python_exe), "-m", "pip", "install",
         "--quiet", "--disable-pip-version-check",
         "--no-warn-script-location"] + PACKAGES,
        check=True,
    )
    print("  [OK] Pacotes instalados")


def step_verify(python_exe: Path) -> bool:
    """Verifica se o Streamlit está acessível."""
    result = subprocess.run(
        [str(python_exe), "-c",
         "import streamlit, plotly, pandas; "
         "print('streamlit=' + streamlit.__version__ + ' '+"
         "'plotly=' + plotly.__version__ + ' '+"
         "'pandas=' + pandas.__version__)"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  [OK] Verificado: {result.stdout.strip()}")
        return True
    print(f"  [ERRO] Verificacao falhou: {result.stderr.strip()[:200]}")
    return False


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara Python embutido para o Streamlit")
    parser.add_argument("--python", default=DEFAULT_PYTHON, metavar="VER",
                        help=f"Versão do Python (padrão: {DEFAULT_PYTHON})")
    parser.add_argument("--force", action="store_true",
                        help="Recria dashboard-env mesmo se já existir")
    args = parser.parse_args()

    SEP = "=" * 62
    print()
    print(SEP)
    print("  BTExtract - Preparando Python embutido para Streamlit")
    print(f"  Python {args.python} | {ARCH}")
    print(SEP)

    DIST_DIR.mkdir(exist_ok=True)

    print("\n[1/5] Download do Python embutido")
    zip_path = step_download(args.python)

    print("\n[2/5] Extracao")
    step_extract(zip_path, args.force)

    print("\n[3/5] Habilitando site-packages")
    step_enable_site_packages()

    print("\n[4/5] Instalando pip")
    python_exe = step_install_pip()

    print("\n[5/5] Instalando Streamlit + dependencias")
    step_install_packages(python_exe)

    print("\n     Verificando instalacao...")
    ok = step_verify(python_exe)

    total_mb = _size_mb(OUTPUT_DIR)
    print()
    print(SEP)
    if ok:
        print(f"  [OK] dashboard-env pronto!")
        print(f"  >> {OUTPUT_DIR}")
        print(f"  Tamanho: {total_mb:.0f} MB")
    else:
        print("  [ERRO] Algo deu errado. Verifique os erros acima.")
        sys.exit(1)
    print(SEP)
    print()


if __name__ == "__main__":
    main()
