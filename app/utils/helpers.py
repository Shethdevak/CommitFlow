import time
import re
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type
from loguru import logger

_MERGE_SUBJECT_RE = re.compile(
    r"^(Merge pull request\b|Merge branch\b|Merge remote-tracking branch\b|Merge\b.*\binto\b)",
    re.IGNORECASE,
)


def is_merge_commit(message: str, parent_count: Optional[int] = None) -> bool:
    """Returns True for merge/PR commits that should not become worklog to-dos."""
    subject = (message or "").strip().split("\n", 1)[0]
    if parent_count is not None and parent_count > 1:
        return True
    return bool(_MERGE_SUBJECT_RE.match(subject))


def with_retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """Decorator to retry a function call with exponential backoff if specific exceptions occur."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_retries = 0
            current_delay = delay
            
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    current_retries += 1
                    if current_retries > retries:
                        logger.error(
                            f"Function '{func.__name__}' failed after {retries} retries. Error: {e}"
                        )
                        raise e
                    
                    logger.warning(
                        f"Function '{func.__name__}' raised {e.__class__.__name__}: {e}. "
                        f"Retrying in {current_delay:.2f}s (Attempt {current_retries}/{retries})..."
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator
