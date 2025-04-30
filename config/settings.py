import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

"""
Configuration settings for the Document Scanner application.
"""

# Load environment variables from .env file
load_dotenv()

# --- API Configuration ---
BASE_URL: str = os.getenv('BASE_URL', 'http://localhost:8081')
API_TOKEN: Optional[str] = os.getenv('API_TOKEN')
INSTANCE_ID: str = os.getenv('INSTANCE_ID', 'whatsapp')
INSTANCE_TOKEN: Optional[str] = os.getenv('INSTANCE_TOKEN')
DOWNLOAD_BASE_DIR: str = os.getcwd()  # Base directory for user data (current working directory)

# --- Timing Settings ---
MAX_WAIT_TIME: int = int(os.getenv('MAX_WAIT_TIME', '300'))  # 5 minutes default wait time

# --- Logging Configuration ---
LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT: str = '%(asctime)s [%(levelname)s] %(message)s'  # Simplified format

# --- Processing Configuration ---
SCAN_VERSIONS: List[Dict[str, str]] = [
    {'name': 'original', 'suffix': ''},
    {'name': 'bw', 'suffix': '_BW'},
    {'name': 'bw_direct', 'suffix': '_BW_direct'}
    # Temporarily disabled versions:
    # {'name': 'magic_color', 'suffix': '_magic_color'},
    # {'name': 'enhanced', 'suffix': '_magic_color_enhanced'}
]

# --- External Tools Configuration ---
# Timeout settings (in seconds)
DEFAULT_COMMAND_TIMEOUT: int = int(os.getenv('DEFAULT_COMMAND_TIMEOUT', '300'))  # 5 minutes
LIBREOFFICE_TIMEOUT: int = int(os.getenv('LIBREOFFICE_TIMEOUT', '120'))  # 2 minutes
GHOSTSCRIPT_TIMEOUT: int = int(os.getenv('GHOSTSCRIPT_TIMEOUT', '120'))  # 2 minutes
SCANNER_TIMEOUT: int = int(os.getenv('SCANNER_TIMEOUT', '180'))  # 3 minutes
PANDOC_TIMEOUT: int = int(os.getenv('PANDOC_TIMEOUT', '60'))  # 1 minute
PDF_TOOLS_TIMEOUT: int = int(os.getenv('PDF_TOOLS_TIMEOUT', '120'))  # 2 minutes

# --- Redis Configuration ---
# If REDIS_ENABLED is set to False or any value that evaluates to False,
# the application will use in-memory storage instead of Redis
REDIS_ENABLED: bool = os.getenv('REDIS_ENABLED', 'true').lower() in ('true', 'yes', 'y', '1')
REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT: int = int(os.getenv('REDIS_PORT', '6379'))  # Changed from 6378 to standard port 6379
REDIS_DB: int = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD: Optional[str] = os.getenv('REDIS_PASSWORD')
REDIS_PREFIX: str = os.getenv('REDIS_PREFIX', 'doc_scanner:')
REDIS_TIMEOUT: int = int(os.getenv('REDIS_TIMEOUT', '5'))  # Connection timeout in seconds
WORKFLOW_STATE_TTL: int = int(os.getenv('WORKFLOW_STATE_TTL', '86400'))  # 24 hours

# --- Celery Configuration ---
# Use Redis as the broker and backend for Celery
CELERY_ENABLED: bool = os.getenv('CELERY_ENABLED', 'true').lower() in ('true', 'yes', 'y', '1')
CELERY_BROKER_URL: str = os.getenv('CELERY_BROKER_URL', f"redis://{':' + REDIS_PASSWORD + '@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
CELERY_RESULT_BACKEND: str = os.getenv('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED: bool = True
CELERY_TASK_TIME_LIMIT: int = int(os.getenv('CELERY_TASK_TIME_LIMIT', '600'))  # 10 minutes
CELERY_TASK_SOFT_TIME_LIMIT: int = int(os.getenv('CELERY_TASK_SOFT_TIME_LIMIT', '540'))  # 9 minutes
CELERY_TASK_SERIALIZER: str = 'json'
CELERY_RESULT_SERIALIZER: str = 'json'
CELERY_ACCEPT_CONTENT: List[str] = ['json']
CELERY_TIMEZONE: str = 'UTC'
CELERY_TASK_DEFAULT_QUEUE: str = 'document_scanner'
CELERY_TASK_DEFAULT_EXCHANGE: str = 'document_scanner'
CELERY_TASK_DEFAULT_ROUTING_KEY: str = 'document_scanner'
CELERY_TASK_DEFAULT_EXCHANGE_TYPE: str = 'direct'
# Retry settings
CELERY_TASK_MAX_RETRIES: int = int(os.getenv('CELERY_TASK_MAX_RETRIES', '3'))
CELERY_TASK_RETRY_DELAY: int = int(os.getenv('CELERY_TASK_RETRY_DELAY', '5'))  # 5 seconds
