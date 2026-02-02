"""
HTTP client configuration and utilities.
"""
import httpx
from config.settings import settings
from core.auth import get_auth_headers


def get_client(timeout: float = 60.0):
    """
    Get configured HTTP client with auth headers.
    
    Args:
        timeout: Request timeout in seconds
    
    Returns:
        httpx.Client instance
    """
    return httpx.Client(
        base_url=settings.FASTAPI_URL,
        headers=get_auth_headers(),
        timeout=httpx.Timeout(timeout)
    )


def handle_http_error(e: Exception, operation: str, logger):
    """
    Handle HTTP errors and return user-friendly message.
    
    Args:
        e: Exception that occurred
        operation: Description of the operation
        logger: Logger instance
    
    Returns:
        Error message string
    """
    if isinstance(e, httpx.HTTPStatusError):
        try:
            error_detail = e.response.json().get('detail', 'Unknown error')
        except:
            error_detail = e.response.text or 'Unknown error'
        logger.error(f"{operation} failed: {error_detail}")
        # Normalize FastAPI/Pydantic validation errors into user-friendly text.
        if isinstance(error_detail, list):
            for item in error_detail:
                loc = item.get("loc", [])
                msg = item.get("msg", "")
                if "email" in loc:
                    return f"{operation} failed: Please enter a valid email address."
                if msg:
                    return f"{operation} failed: {msg}"
            return f"{operation} failed: Invalid input. Please check your form and try again."
        if isinstance(error_detail, str) and error_detail.lower().startswith("repository too large"):
            return f"{operation} failed: {error_detail}"
        return f"{operation} failed: {error_detail}"
    elif isinstance(e, httpx.RequestError):
        logger.error(f"Network error during {operation}: {e}", exc_info=True)
        return f"Network error during {operation}: {e}"
    else:
        logger.error(f"Unexpected error during {operation}: {e}", exc_info=True)
        return f"Unexpected error during {operation}: {e}"
