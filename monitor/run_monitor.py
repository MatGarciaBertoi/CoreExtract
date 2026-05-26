"""
Executor standalone do BTExtract Monitor.
Execute diretamente no Windows, Linux, ou como serviço.

    python run_monitor.py             # loop contínuo (padrão: 3 min)
    python run_monitor.py --once      # executa um ciclo e imprime resultado
    python run_monitor.py --interval 60  # ciclo a cada 60s
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor.btextract_monitor import BTExtractMonitor, DEFAULT_CONFIG

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "btextract_monitor.log"),
            encoding="utf-8",
        ),
    ],
)

# ── Config (pode sobrescrever via env vars ou editando aqui) ──────────────────
CONFIG = {
    **DEFAULT_CONFIG,
    # Descomente e preencha para habilitar OCI auto-reboot:
    # "instance_ocid":   "ocid1.instance.oc1.sa-saopaulo-1.xxxxxx",
    # "oci_config_path": r"C:\Users\matgb\.oci\config",

    # Senha do app Gmail para alertas por e-mail:
    "smtp_config": {
        "user":     os.getenv("MONITOR_SMTP_USER", "enviorhbertoi@gmail.com"),
        "password": os.getenv("MONITOR_SMTP_PASS", ""),
    },
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BTExtract Monitor")
    parser.add_argument("--once",     action="store_true", help="Executa um ciclo e sai")
    parser.add_argument("--interval", type=int, default=180, help="Intervalo em segundos (padrão: 180)")
    args = parser.parse_args()

    monitor = BTExtractMonitor(CONFIG)

    if args.once:
        result = monitor.run_cycle()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        monitor.run_forever(interval_seconds=args.interval)
