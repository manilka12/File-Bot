"""
Logging utilities for the Document Scanner application.

This module provides enhanced logging functionality, including:
1. Consistent log formatting
2. Context injection (task_id, sender_jid, etc.)
3. Filter capabilities
"""

import logging
import functools
from typing import Optional, Dict, Any, Callable

# Create a context-aware filter
class ContextFilter(logging.Filter):
    """Filter that injects contextual information into log records."""
    
    def __init__(self):
        super().__init__()
        self.context = {}
        
    def filter(self, record):
        """Add context data to the log record."""
        # Set default values for required fields
        if not hasattr(record, 'task_id'):
            setattr(record, 'task_id', 'no_task')
            
        if not hasattr(record, 'sender_jid'):
            setattr(record, 'sender_jid', 'system')
            
        # Add context data from the context dict
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


# Global context filter instance
context_filter = ContextFilter()


def setup_logger(name: str, level: str = "INFO", format_str: Optional[str] = None) -> logging.Logger:
    """
    Set up a logger with the context filter.
    
    Args:
        name: Name of the logger
        level: Logging level (INFO, DEBUG, etc.)
        format_str: Optional format string
        
    Returns:
        Logger with context filter applied
    """
    logger = logging.getLogger(name)
    
    # Don't add handlers if they already exist
    if not logger.handlers:
        handler = logging.StreamHandler()
        
        # Use default format if none provided
        if not format_str:
            format_str = '%(asctime)s [%(levelname)s] %(name)s - ' + \
                         '%(task_id)s - %(sender_jid)s - %(message)s'
                         
        formatter = logging.Formatter(format_str)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    # Set level
    logger.setLevel(getattr(logging, level.upper()))
    
    # Add context filter if not already added
    if not any(isinstance(f, ContextFilter) for f in logger.filters):
        logger.addFilter(context_filter)
    
    return logger


def set_context(**kwargs) -> None:
    """
    Set context values for the current thread.
    
    Example:
        set_context(task_id="abc123", sender_jid="user@whatsapp.net")
    """
    for key, value in kwargs.items():
        context_filter.context[key] = value


def get_context(key: str) -> Any:
    """Get a context value by key."""
    return context_filter.context.get(key)


def clear_context() -> None:
    """Clear all context values."""
    context_filter.context.clear()


def with_context(func: Optional[Callable] = None, **default_context):
    """
    Decorator to set and clear context around a function call.
    
    Can be used in two ways:
    
    1. With default context:
       @with_context(task_id="unknown")
       def my_function():
           ...
           
    2. Without default context:
       @with_context
       def my_function():
           ...
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            # Extract context from kwargs
            context_kwargs = {}
            
            # Add defaults
            for key, value in default_context.items():
                context_kwargs[key] = value
                
            # Add any context passed in function call
            for key in list(kwargs.keys()):
                if key.startswith('log_'):
                    context_key = key[4:]  # Remove 'log_' prefix
                    context_kwargs[context_key] = kwargs.pop(key)
            
            old_context = {k: get_context(k) for k in context_kwargs.keys()
                          if get_context(k) is not None}
            
            try:
                set_context(**context_kwargs)
                return f(*args, **kwargs)
            finally:
                # Restore previous context
                clear_context()
                if old_context:
                    set_context(**old_context)
                    
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)