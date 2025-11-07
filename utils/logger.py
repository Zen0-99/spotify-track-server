"""
Structured logging configuration.
"""

import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logging(log_level: str = "INFO"):
    """
    Configure logging with JSON formatting for production.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(log_level.upper())
    
    # Remove existing handlers
    logger.handlers = []
    
    # Console handler with JSON formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level.upper())
    
    # JSON formatter for structured logging
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("spotipy").setLevel(logging.WARNING)
    logging.getLogger("yt_dlp").setLevel(logging.WARNING)
    
    return logger
