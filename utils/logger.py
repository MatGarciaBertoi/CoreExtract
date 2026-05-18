"""
Logger estruturado para Cloud Logging (Google).
Emite JSON com campos padronizados que o Cloud Logging indexa automaticamente,
permitindo filtros, alertas e dashboards no GCP sem configuração extra.
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """
    Formata logs como JSON estruturado compatível com o formato de
    Log Entry do Google Cloud Logging (severity, message, labels, etc.).
    """

    SEVERITY_MAP = {
        logging.DEBUG:    "DEBUG",
        logging.INFO:     "INFO",
        logging.WARNING:  "WARNING",
        logging.ERROR:    "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "severity":   self.SEVERITY_MAP.get(record.levelno, "DEFAULT"),
            "message":    record.getMessage(),
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "logger":     record.name,
            "module":     record.module,
            "function":   record.funcName,
            "line":       record.lineno,
        }

        # Injeta campos extras passados via extra={}
        for key, value in record.__dict__.items():
            if key.startswith("ce_"):  # prefixo BTExtract
                entry[key] = value

        # Stack trace em caso de exceção
        if record.exc_info:
            entry["exception"] = {
                "type":       record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message":    str(record.exc_info[1]),
                "stacktrace": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(entry, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger configurado.
    - Em produção (GCP): JSON estruturado para stdout (Cloud Logging capta).
    - Em desenvolvimento: formato legível colorido.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # já configurado (warm instance)

    is_production = os.environ.get("K_SERVICE") is not None  # Cloud Run/Functions injeta K_SERVICE

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        StructuredFormatter() if is_production else
        logging.Formatter("[%(asctime)s] %(levelname)-8s %(name)s — %(message)s", "%H:%M:%S")
    )

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if not is_production else logging.INFO)
    logger.propagate = False

    return logger
