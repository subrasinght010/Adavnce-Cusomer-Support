# utils/logger.py
import logging
from logging.handlers import TimedRotatingFileHandler
import os

def setup_logger(name: str, log_dir: str = 'logs', level: int = logging.DEBUG) -> logging.Logger:
    """
    Setup logger with file rotation and console output
    
    Args:
        name: Logger name (usually __name__)
        log_dir: Directory for log files
        level: Logging level (INFO or DEBUG)
    
    Returns:
        Configured logger
    """
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # Prevent duplicate handlers
    
    # File handler - INFO and above
    file_handler = TimedRotatingFileHandler(
        filename=f'{log_dir}/app.log',
        when='D',
        interval=1,
        backupCount=2
    )
    file_handler.setLevel(level)
    
    # Console handler - DEBUG and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Usage
if __name__ == "__main__":
    logger = setup_logger(__name__)