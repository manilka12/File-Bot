import os

"""
Configuration settings for the Document Scanner application.
"""

# --- API Configuration ---
BASE_URL = 'http://arm:8081'
API_TOKEN = 'MnImanilka'
INSTANCE_ID = "whatsapp"
INSTANCE_TOKEN = "D9EC72F9C904-4812-A3A9-36CE34CBE1F2"
DOWNLOAD_BASE_DIR = os.getcwd()  # Base directory for user data (current working directory)

# --- Logging Configuration ---
LOG_LEVEL = "INFO"
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
