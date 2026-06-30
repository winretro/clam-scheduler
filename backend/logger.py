import os
import logging

# Read the environment variable, default to INFO
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

# Configure a standardized root logger
logging.basicConfig(
    level=log_level,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Explicitly silence third-party noise unless we are in DEBUG mode
if log_level != logging.DEBUG:
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("clam-scheduler")
