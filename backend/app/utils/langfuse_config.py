"""
Langfuse configuration for LLM observability and tracing.
"""
import os
from typing import Any, Optional
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse.types import TraceContext

from ..core.logging import get_logger

logger = get_logger(__name__)


class LangfuseConfig:
    """Langfuse configuration singleton."""
    
    _instance: Optional['LangfuseConfig'] = None
    _callback_handler: Optional[CallbackHandler] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize Langfuse configuration."""
        if not hasattr(self, 'initialized'):
            self.secret_key = os.getenv("LANGFUSE_SECRET_KEY")
            self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
            self.base_url = os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
            self.enabled = bool(self.secret_key and self.public_key)
            
            if self.enabled:
                logger.info(f"Langfuse enabled | base_url: {self.base_url}")
            else:
                logger.warning("Langfuse disabled - missing API keys")
            
            self.initialized = True
    
    def get_callback_handler(
        self,
        trace_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        tags: Optional[list] = None
    ) -> Optional[CallbackHandler]:
        """
        Get Langfuse callback handler for tracing.
        
        Args:
            trace_name: Name of the trace
            user_id: User identifier
            session_id: Session identifier
            metadata: Additional metadata
            tags: Tags for filtering
        
        Returns:
            CallbackHandler instance or None if disabled
        """
        if not self.enabled:
            return None
        
        try:
            # Initialize handler - uses env vars automatically
            handler = CallbackHandler()
            
            # Set trace properties as attributes
            if trace_name:
                handler.trace_name = trace_name
            if user_id:
                handler.user_id = user_id
            if session_id:
                handler.session_id = session_id
            if metadata:
                handler.metadata = metadata
            if tags:
                handler.tags = tags
            
            logger.debug(f"Created Langfuse callback handler | trace: {trace_name}")
            return handler
        
        except Exception as e:
            logger.error(f"Failed to create Langfuse callback handler: {e}", exc_info=True)
            return None

    def create_trace(
        self,
        trace_name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        tags: Optional[list] = None,
    ) -> Optional[str]:
        """
        Create a root Langfuse trace and return its id.
        """
        if not self.enabled:
            return None
        try:
            client = Langfuse()
            trace_id = client.create_trace_id()
            client.update_current_trace(
                name=trace_name,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata,
                tags=tags,
            )
            return trace_id
        except Exception as e:
            logger.error(f"Failed to create Langfuse trace: {e}", exc_info=True)
            return None

    def get_callback_handler_for_trace(
        self,
        trace_id: Optional[str],
        update_trace: bool = True,
    ) -> Optional[CallbackHandler]:
        """
        Create a Langfuse callback handler attached to an existing trace id.
        """
        if not self.enabled or not trace_id:
            return None
        try:
            return CallbackHandler(
                trace_context=TraceContext(trace_id=str(trace_id)),
                update_trace=bool(update_trace),
            )
        except Exception as e:
            logger.error(f"Failed to create Langfuse handler for trace: {e}", exc_info=True)
            return None
    
    def flush(self):
        """Flush any pending traces."""
        if self._callback_handler:
            try:
                self._callback_handler.flush()
            except Exception as e:
                logger.error(f"Error flushing Langfuse traces: {e}")


# Global instance
langfuse_config = LangfuseConfig()


def get_langfuse_handler(
    trace_name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    tags: Optional[list] = None
) -> Optional[CallbackHandler]:
    """
    Convenience function to get Langfuse callback handler.
    
    Args:
        trace_name: Name of the trace
        user_id: User identifier
        session_id: Session identifier  
        metadata: Additional metadata
        tags: Tags for filtering
    
    Returns:
        CallbackHandler instance or None if disabled
    """
    return langfuse_config.get_callback_handler(
        trace_name=trace_name,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
        tags=tags
    )


def create_langfuse_trace(
    trace_name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    tags: Optional[list] = None,
) -> Optional[str]:
    """
    Create a Langfuse trace and return its id.
    """
    return langfuse_config.create_trace(
        trace_name=trace_name,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
        tags=tags,
    )


def get_langfuse_handler_for_trace(
    trace_id: Optional[str],
    update_trace: bool = True,
) -> Optional[CallbackHandler]:
    """
    Create a callback handler attached to an existing trace id.
    """
    return langfuse_config.get_callback_handler_for_trace(
        trace_id=trace_id,
        update_trace=update_trace,
    )
