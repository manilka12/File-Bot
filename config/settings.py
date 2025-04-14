import os
from dotenv import load_dotenv

"""
Configuration settings for the Document Scanner application.
"""

# Load environment variables from .env file
load_dotenv()

# --- API Configuration ---
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8081')
API_TOKEN = os.getenv('API_TOKEN')
INSTANCE_ID = os.getenv('INSTANCE_ID', 'whatsapp')
INSTANCE_TOKEN = os.getenv('INSTANCE_TOKEN')
DOWNLOAD_BASE_DIR = os.getcwd()  # Base directory for user data (current working directory)

# --- Logging Configuration ---
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'  # Simplified format

# --- Processing Configuration ---
SCAN_VERSIONS = [
    {'name': 'original', 'suffix': ''},
    {'name': 'bw', 'suffix': '_BW'},
    {'name': 'bw_direct', 'suffix': '_BW_direct'}
    # Temporarily disabled versions:
    # {'name': 'magic_color', 'suffix': '_magic_color'},
    # {'name': 'enhanced', 'suffix': '_magic_color_enhanced'}
]
