"""
Contexto de requisição: ID único, timing e metadados de rastreamento.
Permite correlacionar logs de uma mesma requisição no Cloud Logging.
"""
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestContext:
    """
    Criado no início de cada requisição HTTP e passado pelo pipeline.
    O request_id aparece em todos os logs, permitindo filtrar
    todos os eventos de uma requisição no Cloud Logging com:
        jsonPayload.ce_request_id="<id>"
    """
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.monotonic)
    file_hash: Optional[str] = None       # MD5 do arquivo (cache / deduplicação)
    filename: Optional[str] = None
    file_size_bytes: int = 0
    chars_extracted: int = 0
    was_truncated: bool = False
    gemini_input_tokens: int = 0
    gemini_output_tokens: int = 0
    processing_steps: list[str] = field(default_factory=list)

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def step(self, name: str) -> None:
        """Registra uma etapa do pipeline para rastreamento."""
        self.processing_steps.append(f"{name}@{self.elapsed_ms}ms")

    def compute_file_hash(self, file_bytes: bytes) -> str:
        self.file_hash = hashlib.md5(file_bytes).hexdigest()
        return self.file_hash

    def to_log_extras(self) -> dict:
        """Retorna campos prontos para injetar no logger via extra={}."""
        return {
            "ce_request_id":    self.request_id,
            "ce_filename":      self.filename,
            "ce_file_hash":     self.file_hash,
            "ce_elapsed_ms":    self.elapsed_ms,
            "ce_steps":         " → ".join(self.processing_steps),
        }

    def to_response_meta(self) -> dict:
        """Campos de metadados incluídos na resposta JSON ao cliente."""
        return {
            "request_id":          self.request_id,
            "processing_time_ms":  self.elapsed_ms,
            "chars_extracted":     self.chars_extracted,
            "was_truncated":       self.was_truncated,
            "gemini_tokens_used": {
                "input":  self.gemini_input_tokens,
                "output": self.gemini_output_tokens,
            },
            "pipeline_steps":      self.processing_steps,
        }
