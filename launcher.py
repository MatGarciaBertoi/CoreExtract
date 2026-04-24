"""
CoreExtract — Launcher para distribuição Windows.

Este é o ponto de entrada do executável gerado pelo PyInstaller.
Responsabilidades:
  1. Iniciar o servidor FastAPI (uvicorn) em thread separada
  2. Aguardar o servidor ficar pronto
  3. Abrir o navegador padrão em http://127.0.0.1:8080
  4. Manter o processo vivo até o usuário fechar a janela (ou Ctrl+C)
  5. Mostrar ícone na bandeja do sistema (system tray) com opção de fechar
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ── Garante que o diretório do executável está no sys.path ───────────────────
# Necessário para que os imports dos módulos do CoreExtract funcionem.
if getattr(sys, "frozen", False):
    # Rodando como .exe — _MEIPASS contém os arquivos extraídos
    _BASE = Path(sys._MEIPASS)           # type: ignore[attr-defined]
    sys.path.insert(0, str(_BASE))
else:
    # Rodando a partir do código-fonte
    _BASE = Path(__file__).parent
    sys.path.insert(0, str(_BASE))

PORT = 8080
HOST = "127.0.0.1"
URL  = f"http://{HOST}:{PORT}"


# ─────────────────────────────────────────────────────────────────────────────
#  Verifica se a porta já está em uso (instância anterior aberta)
# ─────────────────────────────────────────────────────────────────────────────

def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    """Aguarda o servidor aceitar conexões. Retorna True se subiu a tempo."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_in_use(host, port):
            return True
        time.sleep(0.2)
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Thread do servidor
# ─────────────────────────────────────────────────────────────────────────────

def _run_server() -> None:
    """Inicia o uvicorn em modo produção (sem reload)."""
    import uvicorn
    # Importa o app depois — garante que sys.path já está configurado
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="warning",   # reduz barulho no console
        access_log=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  System Tray (opcional — só carrega se pystray estiver disponível)
# ─────────────────────────────────────────────────────────────────────────────

def _start_tray(stop_event: threading.Event) -> None:
    """
    Mostra ícone na bandeja do sistema com menu:
      • Abrir CoreExtract  → abre o navegador
      • Fechar             → encerra o processo
    Falha silenciosamente se pystray/Pillow não estiverem instalados.
    """
    try:
        import pystray
        from PIL import Image, ImageDraw

        # Ícone simples 64×64 gerado programaticamente (azul com "C")
        img = Image.new("RGB", (64, 64), color=(10, 22, 40))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(26, 107, 255))
        draw.text((20, 16), "C", fill=(255, 255, 255))

        def on_open(_icon, _item):
            webbrowser.open(URL)

        def on_quit(icon, _item):
            stop_event.set()
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Abrir CoreExtract", on_open, default=True),
            pystray.MenuItem("Fechar CoreExtract", on_quit),
        )
        icon = pystray.Icon("CoreExtract", img, "CoreExtract · RH Inteligente", menu)
        icon.run()
    except Exception:
        # pystray/Pillow não instalados — sem tray, sem problema
        stop_event.wait()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 52, flush=True)
    print("  CoreExtract · RH Inteligente", flush=True)
    print(f"  Iniciando servidor em {URL}", flush=True)
    print("=" * 52, flush=True)

    # Se já existe uma instância rodando, apenas abre o navegador
    if _port_in_use(HOST, PORT):
        print("  Servidor ja rodando — abrindo navegador...", flush=True)
        webbrowser.open(URL)
        return

    # Inicia o servidor em thread daemon
    server_thread = threading.Thread(target=_run_server, daemon=True, name="uvicorn")
    server_thread.start()

    # Aguarda o servidor ficar pronto
    print("  Aguardando servidor...", flush=True)
    if not _wait_for_server(HOST, PORT, timeout=30):
        print("  ERRO: Servidor nao respondeu em 30s.", flush=True)
        input("  Pressione Enter para fechar...")
        sys.exit(1)

    print(f"  Servidor pronto! Abrindo {URL}", flush=True)
    time.sleep(0.3)  # pequena pausa para garantir que o FastAPI registrou todas as rotas
    webbrowser.open(URL)

    # Mantém o processo vivo via system tray (ou simplesmente esperando)
    stop_event = threading.Event()
    _start_tray(stop_event)


if __name__ == "__main__":
    main()
