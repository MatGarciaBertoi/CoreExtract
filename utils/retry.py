"""
Decorator de retry com exponential backoff e jitter.
Usado nas chamadas ao Vertex AI / Gemini para lidar com
rate limiting (429) e erros transitórios de rede.
"""
import functools
import random
import time
from collections.abc import Callable
from typing import TypeVar

from utils.logger import get_logger

logger = get_logger("utils.retry")

F = TypeVar("F", bound=Callable)


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    non_retryable_exceptions: tuple = (ValueError, TypeError),
) -> Callable[[F], F]:
    """
    Decorator que re-tenta a função em caso de exceção retryable.

    Args:
        max_attempts:           Número máximo de tentativas (incluindo a primeira).
        base_delay:             Tempo base de espera em segundos.
        max_delay:              Teto de espera (clamped).
        backoff_factor:         Multiplicador exponencial a cada tentativa.
        retryable_exceptions:   Tipos de exceção que ativam retry.
        non_retryable_exceptions: Tipos que interrompem imediatamente (sem retry).

    Exemplo:
        @with_retry(max_attempts=3, base_delay=1.5)
        def call_gemini(prompt: str) -> str:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except non_retryable_exceptions as exc:
                    logger.warning(
                        "Exceção não-retryable em '%s' (tentativa %d/%d): %s",
                        func.__name__, attempt, max_attempts, exc,
                    )
                    raise

                except retryable_exceptions as exc:
                    last_exception = exc

                    if attempt == max_attempts:
                        break

                    # Exponential backoff + jitter (evita thundering herd)
                    delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    jitter = delay * random.uniform(0.1, 0.3)
                    wait = delay + jitter

                    logger.warning(
                        "Tentativa %d/%d falhou em '%s': %s. Aguardando %.2fs...",
                        attempt, max_attempts, func.__name__, exc, wait,
                    )
                    time.sleep(wait)

            logger.error(
                "Todas as %d tentativas falharam em '%s'.",
                max_attempts, func.__name__,
            )
            raise last_exception  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]
    return decorator
