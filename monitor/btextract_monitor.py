"""
BTExtract Monitor — auto-recuperação em 3 etapas
═══════════════════════════════════════════════════════════════════════════════
Etapa 1 → Retry HTTP:      aguarda 30s e tenta novamente antes de agir
Etapa 2 → SSH restart:     sudo systemctl restart btextract btextract-redirect
Etapa 3 → OCI force reboot: reinicia a VM via Oracle Cloud API (se configurado)
Etapa 4 → Alerta e-mail:   notifica que intervenção manual é necessária

Integração no Monitor de Projetos:
    from monitor.btextract_monitor import BTExtractMonitor, DEFAULT_CONFIG
    monitor = BTExtractMonitor(DEFAULT_CONFIG)
    status = monitor.run_cycle()   # dict padronizado — pronto para dashboard
    # ou loop contínuo:
    monitor.run_forever(interval_seconds=180)

Retorno de run_cycle():
    {
        "service":             "btextract",
        "status":              "healthy" | "degraded" | "down",
        "action_taken":        None | "ssh_restart" | "oci_reboot" | "alert_sent",
        "consecutive_failures": int,
        "timestamp":           "2026-05-26T12:00:00",
        "message":             str,
        "url":                 str,
    }
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
import time
from datetime import datetime
from email.mime.text import MIMEText
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("btextract_monitor")

# ─────────────────────────────────────────────────────────────────────────────
# Configuração padrão — sobrescreva ao instanciar a classe
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG: dict = {
    # Endpoint de saúde do BTExtract
    "health_url":       "https://btextract-bertoi.duckdns.org/health",

    # SSH — acesso ao Oracle VM para restart de serviço
    "ssh_host":         "147.15.87.102",
    "ssh_user":         "opc",
    "ssh_key_path":     r"C:\Users\matgb\.ssh\oracle.key",

    # OCI API — reboot automático da VM quando SSH também falhar
    # Preencha com os valores do Oracle Cloud Console
    # (Identity → Users → API Keys)
    "instance_ocid":    os.getenv("OCI_INSTANCE_OCID", ""),
    "oci_config_path":  os.getenv("OCI_CONFIG_PATH", r"C:\Users\matgb\.oci\config"),

    # Alertas por e-mail
    "alert_email":      "matheusbertoi080@gmail.com",
    "smtp_config": {
        "user":     os.getenv("MONITOR_SMTP_USER",  "enviorhbertoi@gmail.com"),
        "password": os.getenv("MONITOR_SMTP_PASS",  ""),   # app-password Gmail
    },
}


# ─────────────────────────────────────────────────────────────────────────────
class BTExtractMonitor:
    """Monitor com auto-recuperação em múltiplas etapas para o BTExtract."""

    def __init__(self, config: dict | None = None):
        cfg = {**DEFAULT_CONFIG, **(config or {})}
        self.health_url      = cfg["health_url"]
        self.ssh_host        = cfg["ssh_host"]
        self.ssh_user        = cfg["ssh_user"]
        self.ssh_key_path    = cfg["ssh_key_path"]
        self.instance_ocid   = cfg.get("instance_ocid", "")
        self.oci_config_path = cfg.get("oci_config_path", "")
        self.alert_email     = cfg.get("alert_email", "")
        self.smtp_config     = cfg.get("smtp_config", {})

        # Estado interno — acompanha falhas consecutivas entre ciclos
        self.consecutive_failures: int = 0
        self._last_alert_sent: Optional[str] = None   # evita flood de e-mails

    # ── Verificação HTTP ──────────────────────────────────────────────────────
    def check_health(self, timeout: int = 10) -> bool:
        """Retorna True se o endpoint /health responder corretamente."""
        try:
            r = requests.get(self.health_url, timeout=timeout, verify=False)
            return r.status_code == 200 and "healthy" in r.text
        except Exception:
            return False

    # ── Etapa 2: SSH restart ──────────────────────────────────────────────────
    def restart_via_ssh(self) -> bool:
        """Tenta reiniciar os serviços via SSH. Retorna True se serviço voltou."""
        try:
            import paramiko  # instalado via requirements-monitor.txt
        except ImportError:
            logger.error("paramiko não instalado — execute: pip install paramiko")
            return False

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                self.ssh_host,
                username=self.ssh_user,
                key_filename=self.ssh_key_path,
                timeout=15,
            )
            cmd = (
                "sudo systemctl restart btextract btextract-redirect && "
                "sleep 6 && systemctl is-active btextract"
            )
            _, stdout, _ = client.exec_command(cmd)
            result = stdout.read().decode().strip()
            client.close()
            return result == "active"
        except Exception as exc:
            logger.error("SSH restart falhou: %s", exc)
            return False

    # ── Etapa 3: OCI recovery inteligente ────────────────────────────────────
    def reboot_via_oci(self) -> bool:
        """
        Recuperação inteligente via OCI API — lida com 4 cenários:
          RUNNING   → RESET  (serviços travados mas VM viva)
          STOPPING  → aguarda até STOPPED/RUNNING (max 3 min), depois START se necessário
          STOPPED   → START
          STARTING  → aguarda boot (max 2 min)
        Retorna True se uma ação de recuperação foi enviada com sucesso.
        """
        if not self.instance_ocid or not self.oci_config_path:
            logger.warning("OCI reboot ignorado: instance_ocid ou oci_config_path não configurados")
            return False
        try:
            import oci
            import warnings as _w
            _w.filterwarnings("ignore")
            cfg     = oci.config.from_file(self.oci_config_path)
            compute = oci.core.ComputeClient(cfg)

            state = compute.get_instance(self.instance_ocid).data.lifecycle_state
            logger.warning("OCI estado da instância: %s", state)

            if state == "RUNNING":
                # VM viva mas serviço não responde → RESET
                compute.instance_action(self.instance_ocid, "RESET")
                logger.warning("OCI RESET enviado (VM estava RUNNING)")
                return True

            elif state in ("STOPPING", "STOPPED"):
                # Oracle fez manutenção/migração — aguarda estabilizar
                logger.warning("OCI: VM em %s — aguardando transição (max 3 min)...", state)
                for _ in range(36):
                    time.sleep(5)
                    state = compute.get_instance(self.instance_ocid).data.lifecycle_state
                    logger.info("OCI estado: %s", state)
                    if state == "STOPPED":
                        compute.instance_action(self.instance_ocid, "START")
                        logger.warning("OCI START enviado após STOPPED")
                        return True
                    elif state == "RUNNING":
                        logger.info("OCI: VM voltou RUNNING sozinha (migração Oracle)")
                        return True  # voltou; SSH restart vai agir depois
                logger.error("OCI: timeout aguardando transição de %s", state)
                return False

            elif state == "STARTING":
                # Boot em andamento — apenas aguarda
                logger.info("OCI: VM já está iniciando (STARTING) — aguardando boot...")
                return True

            else:
                logger.error("OCI: estado inesperado '%s' — sem ação automática", state)
                return False

        except Exception as exc:
            logger.error("OCI recovery falhou: %s", exc)
            return False

    # ── Notificação por e-mail ────────────────────────────────────────────────
    def _send_alert(self, subject: str, body: str) -> None:
        """Envia alerta por e-mail (anti-flood: máx 1 por assunto a cada 30 min)."""
        if not self.alert_email or not self.smtp_config.get("password"):
            return
        # Anti-flood: não reenvia o mesmo assunto em menos de 30 min
        key = f"{subject}:{datetime.utcnow().strftime('%Y-%m-%d %H:%M')[:13]}"
        if self._last_alert_sent == key:
            return
        self._last_alert_sent = key

        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = f"[BTExtract Monitor] {subject}"
            msg["From"]    = self.smtp_config["user"]
            msg["To"]      = self.alert_email
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
                srv.login(self.smtp_config["user"], self.smtp_config["password"])
                srv.send_message(msg)
            logger.info("Alerta enviado: %s", subject)
        except Exception as exc:
            logger.error("Falha ao enviar alerta: %s", exc)

    # ── Ciclo principal ───────────────────────────────────────────────────────
    def run_cycle(self) -> dict:
        """
        Executa um ciclo completo de monitoramento e auto-recuperação.
        Retorna dict padronizado para integração com dashboard de projetos.
        """
        now = datetime.utcnow().isoformat(timespec="seconds")
        base = {
            "service":              "btextract",
            "url":                  self.health_url,
            "timestamp":            now,
            "action_taken":         None,
            "consecutive_failures": self.consecutive_failures,
        }

        # ── Serviço saudável ──────────────────────────────────────────────────
        if self.check_health():
            self.consecutive_failures = 0
            return {**base, "status": "healthy", "message": "Serviço respondendo normalmente"}

        # ── Primeira falha: aguarda 30s e re-testa antes de agir ─────────────
        self.consecutive_failures += 1
        logger.warning("BTExtract sem resposta (falha #%d)", self.consecutive_failures)

        if self.consecutive_failures == 1:
            logger.info("Aguardando 30s para retry...")
            time.sleep(30)
            if self.check_health():
                self.consecutive_failures = 0
                return {**base, "status": "healthy", "message": "Recuperado após retry automático"}

        # ── Etapa 2: SSH restart ──────────────────────────────────────────────
        logger.warning("[Etapa 2] Tentando restart via SSH...")
        if self.restart_via_ssh():
            time.sleep(10)
            if self.check_health():
                self.consecutive_failures = 0
                self._send_alert(
                    "Serviço reiniciado automaticamente",
                    f"BTExtract estava indisponível.\n"
                    f"Ação: restart via SSH bem-sucedido às {now} UTC.\n"
                    f"Serviço voltou ao normal.",
                )
                return {
                    **base,
                    "status":       "healthy",
                    "action_taken": "ssh_restart",
                    "message":      "Recuperado via SSH restart",
                }

        # ── Etapa 3: OCI force reboot ─────────────────────────────────────────
        logger.error("[Etapa 3] SSH ineficaz. Tentando OCI force reboot...")
        if self.reboot_via_oci():
            self._send_alert(
                "VM reiniciada automaticamente via OCI",
                f"BTExtract não respondia após SSH restart.\n"
                f"Ação: VM reiniciada via Oracle Cloud API às {now} UTC.\n"
                f"Serviço deve voltar em ~60 segundos.",
            )
            return {
                **base,
                "status":       "down",
                "action_taken": "oci_reboot",
                "message":      "VM reiniciada via OCI API — aguardando boot (~60s)",
            }

        # ── Etapa 4: Alerta manual ────────────────────────────────────────────
        logger.error("[Etapa 4] Todas as recuperações automáticas falharam. Alertando.")
        self._send_alert(
            f"ALERTA CRÍTICO: BTExtract indisponível ({self.consecutive_failures} falhas)",
            f"BTExtract em {self.health_url} não responde.\n"
            f"Falhas consecutivas: {self.consecutive_failures}\n"
            f"SSH restart: falhou\n"
            f"OCI reboot: não configurado ou falhou\n\n"
            f"Acesse: https://cloud.oracle.com → Compute → Instances\n"
            f"e clique em Actions → Reboot → Force reboot.",
        )
        return {
            **base,
            "status":       "down",
            "action_taken": "alert_sent",
            "message":      f"Indisponível há {self.consecutive_failures} ciclos. Alerta enviado. Intervenção manual necessária.",
        }

    # ── Loop contínuo ─────────────────────────────────────────────────────────
    def run_forever(self, interval_seconds: int = 180) -> None:
        """Executa monitoramento contínuo. Bloqueante — rode em thread/processo separado."""
        logger.info("Monitor BTExtract iniciado — verificando a cada %ds", interval_seconds)
        while True:
            try:
                status = self.run_cycle()
                level = logging.INFO if status["status"] == "healthy" else logging.WARNING
                logger.log(level, "[%s] %s", status["status"].upper(), status["message"])
            except Exception as exc:
                logger.error("Erro inesperado no ciclo de monitoramento: %s", exc)
            time.sleep(interval_seconds)
