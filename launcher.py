"""
BTExtract — Launcher para distribuição Windows.

Ponto de entrada do executável (PyInstaller) e do run.bat.
Responsabilidades:
  1. Iniciar FastAPI (uvicorn) na porta 8080 — thread interna
  2. Iniciar Streamlit (dashboard) na porta 8081 — subprocesso
  3. Aguardar ambos ficarem prontos
  4. Abrir o navegador em ambas as URLs
  5. Ícone na bandeja com acesso rápido a cada interface
  6. Encerrar ambos os serviços ao fechar
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ── Base do projeto ───────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Rodando como .exe gerado pelo PyInstaller
    _BASE    = Path(sys._MEIPASS)           # type: ignore[attr-defined]  bundle temp
    _APP_DIR = Path(sys.executable).parent  # pasta real de instalação (estável)
    sys.path.insert(0, str(_BASE))
else:
    _BASE    = Path(__file__).parent
    _APP_DIR = _BASE

HOST       = "127.0.0.1"
PORT_API   = 8080
PORT_DASH  = 8081
URL_API    = f"http://{HOST}:{PORT_API}"
URL_DASH   = f"http://{HOST}:{PORT_DASH}"

_st_proc: subprocess.Popen | None = None   # handle do processo Streamlit


# ─────────────────────────────────────────────────────────────────────────────
#  Utilitários de rede
# ─────────────────────────────────────────────────────────────────────────────

def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    """Aguarda o servidor aceitar conexões TCP. Retorna True se subiu a tempo."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_in_use(host, port):
            return True
        time.sleep(0.25)
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  FastAPI — thread interna
# ─────────────────────────────────────────────────────────────────────────────

def _run_api() -> None:
    """Inicia o uvicorn com o app FastAPI."""
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT_API,
        reload=False,
        log_level="warning",
        access_log=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Streamlit — subprocesso separado
# ─────────────────────────────────────────────────────────────────────────────

def _streamlit_cmd() -> list[str]:
    """
    Monta o comando para iniciar o Streamlit dependendo do contexto:
      • frozen (.exe)   → Python embutido em {app}/dashboard-env/python.exe
      • desenvolvimento → venv/Scripts/streamlit.exe
    """
    # dashboard.py fica sempre na pasta de instalação / raiz do projeto
    dashboard  = str(_APP_DIR / "dashboard.py")
    extra_args = [
        "--server.port",              str(PORT_DASH),
        "--server.headless",          "true",
        "--server.address",           HOST,
        "--browser.gatherUsageStats", "false",
    ]

    if getattr(sys, "frozen", False):
        # Distribuição: Python embutido gerado pelo prepare_streamlit_embed.py
        embedded_py = _APP_DIR / "dashboard-env" / "python.exe"
        if embedded_py.exists():
            return [str(embedded_py), "-m", "streamlit", "run", dashboard] + extra_args
        # Fallback: Python do sistema
        return [sys.executable, "-m", "streamlit", "run", dashboard] + extra_args

    # Desenvolvimento: usa venv do projeto
    for candidate in [
        _BASE / "venv" / "Scripts" / "streamlit.exe",
        _BASE / "venv" / "bin"     / "streamlit",
    ]:
        if candidate.exists():
            return [str(candidate), "run", dashboard] + extra_args

    return ["streamlit", "run", dashboard] + extra_args


def _start_streamlit() -> subprocess.Popen:
    """Inicia o Streamlit como subprocesso, passando o path da sessão via env."""
    global _st_proc
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    env   = os.environ.copy()
    env["CE_SESSION_PATH"] = str(_APP_DIR / "last_session.json")
    _st_proc = subprocess.Popen(
        _streamlit_cmd(),
        cwd=str(_APP_DIR),
        env=env,
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return _st_proc


def _stop_streamlit() -> None:
    """Encerra o subprocesso do Streamlit com segurança."""
    global _st_proc
    if _st_proc and _st_proc.poll() is None:
        try:
            if sys.platform == "win32":
                _st_proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                _st_proc.terminate()
            _st_proc.wait(timeout=5)
        except Exception:
            _st_proc.kill()
        finally:
            _st_proc = None


# ─────────────────────────────────────────────────────────────────────────────
#  System Tray
# ─────────────────────────────────────────────────────────────────────────────

def _start_tray(stop_event: threading.Event) -> None:
    """
    Ícone na bandeja do sistema com menu para ambas as interfaces.
    Falha silenciosamente se pystray/Pillow não estiverem disponíveis.
    """
    try:
        import pystray
        from PIL import Image, ImageDraw

        # Ícone 64×64 gerado programaticamente
        img = Image.new("RGB", (64, 64), color=(10, 22, 40))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(26, 107, 255))
        draw.text((20, 16), "C", fill=(255, 255, 255))

        def on_open_api(_icon, _item):
            webbrowser.open(URL_API)

        def on_open_dash(_icon, _item):
            webbrowser.open(URL_DASH)

        def on_quit(icon, _item):
            stop_event.set()
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("🧠  Abrir BTExtract   (8080)", on_open_api, default=True),
            pystray.MenuItem("📊  Abrir Dashboard     (8081)", on_open_dash),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("✖  Fechar BTExtract",         on_quit),
        )
        icon = pystray.Icon("BTExtract", img, "BTExtract · RH Inteligente", menu)
        icon.run()
    except Exception:
        # Sem pystray — aguarda sinal de parada
        stop_event.wait()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 56, flush=True)
    print("  BTExtract - RH Inteligente", flush=True)
    print("=" * 56, flush=True)

    # ── FastAPI ───────────────────────────────────────────────
    if _port_in_use(HOST, PORT_API):
        print(f"  [OK] API ja rodando      -> {URL_API}", flush=True)
    else:
        threading.Thread(target=_run_api, daemon=True, name="uvicorn").start()
        print(f"  [>>] Iniciando API       -> {URL_API}", flush=True)

    # ── Streamlit ─────────────────────────────────────────────
    if _port_in_use(HOST, PORT_DASH):
        print(f"  [OK] Dashboard ja rodando -> {URL_DASH}", flush=True)
    else:
        _start_streamlit()
        print(f"  [>>] Iniciando Dashboard -> {URL_DASH}", flush=True)

    # ── Aguarda ambos ficarem prontos ─────────────────────────
    print("", flush=True)
    print("  [...] Aguardando servicos...", flush=True)

    api_ok  = _wait_for_server(HOST, PORT_API,  timeout=30)
    dash_ok = _wait_for_server(HOST, PORT_DASH, timeout=45)   # Streamlit demora mais

    print("", flush=True)
    if api_ok:
        print(f"  [OK] BTExtract pronto  -> {URL_API}", flush=True)
    else:
        print(f"  [ERRO] BTExtract NAO respondeu em 30s!", flush=True)

    if dash_ok:
        print(f"  [OK] Dashboard pronto    -> {URL_DASH}", flush=True)
    else:
        print(f"  [AVISO] Dashboard ainda carregando - abrindo assim mesmo.", flush=True)

    print("", flush=True)
    print("  Minimize esta janela. Use o icone na bandeja para acessar.", flush=True)
    print("  Pressione Ctrl+C para encerrar todos os servicos.", flush=True)
    print("=" * 56, flush=True)

    # ── Abre o navegador ──────────────────────────────────────
    if api_ok:
        time.sleep(0.3)
        webbrowser.open(URL_API)
    if dash_ok or True:  # tenta abrir dashboard mesmo se não confirmado
        time.sleep(0.5)
        webbrowser.open(URL_DASH)

    # ── Mantém vivo via tray (ou Ctrl+C) ─────────────────────
    stop_event = threading.Event()

    def _on_signal(sig, frame):
        print("\n  🛑  Encerrando serviços...", flush=True)
        _stop_streamlit()
        stop_event.set()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    _start_tray(stop_event)   # bloqueia até o usuário fechar pelo tray ou Ctrl+C
    _stop_streamlit()


if __name__ == "__main__":
    main()
