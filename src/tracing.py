import functools
from typing import Any, Callable, Optional
from .config import settings
from .logger import get_logger

logger = get_logger("tracing")
if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
    try:
        from langfuse import observe

        logger.info("Langfuse observability client initialized successfully.")
    except ImportError as exc:
        logger.warning(
            "Failed to import Langfuse decorators. Continuing without external tracing.",
            extra={"error": str(exc)},
        )
        observe = None
else:
    logger.info(
        "Langfuse credentials not detected. Observability tracing will fall back to local logger."
    )
    observe = None


def get_trace_handler() -> Optional[Any]:
    """
    Returns a tracing handler if Langfuse is active.
    """
    if observe:
        return True
    return None


def trace_agent_step(step_name: str):
    """
    A decorator to trace LangGraph steps.
    Logs standard step actions and publishes span data to Langfuse if enabled.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if observe:
            func = observe(name=step_name, as_type="span")(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.info(f"Executing Agent Step: {step_name}", extra={"step": step_name})
            try:
                result = func(*args, **kwargs)
                logger.info(
                    f"Finished Agent Step: {step_name}",
                    extra={"step": step_name, "status": "success"},
                )
                return result
            except Exception as exc:
                logger.error(
                    f"Agent Step Failed: {step_name}",
                    extra={"step": step_name, "status": "error", "error": str(exc)},
                    exc_info=True,
                )
                raise exc

        return wrapper

    return decorator
