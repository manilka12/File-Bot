"""
Main application entry point for the Document Scanner service.
"""

import time
import logging
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import LOG_LEVEL, LOG_FORMAT
from utils.logging_utils import setup_logger, set_context
from app.whatsapp_client import WhatsAppClient
from app.workflow_manager import WorkflowManager

def setup_logging():
    """Configure logging for the application."""
    # Set default context values for root logger
    set_context(task_id="main", sender_jid="system")
    
    # Setup root logger with our utilities
    return setup_logger("document_scanner", LOG_LEVEL, LOG_FORMAT)

def main():
    """Main entry point for the application."""
    logger = setup_logging()
    logger.info("Starting Document Scanner WhatsApp service...")
    
    try:
        # Initialize WhatsApp client
        whatsapp_client = WhatsAppClient()
        
        # Initialize workflow manager
        workflow_manager = WorkflowManager(whatsapp_client)
        
        # Define message handler callback
        def on_message(data):
            workflow_manager.handle_message(data)
        
        # Define placeholder callbacks
        def on_qrcode(data):
            pass
            
        def on_connection(data):
            pass
        
        # Create and connect WebSocket
        logger.info("Connecting WebSocket for real-time messaging...")
        websocket_manager = whatsapp_client.create_websocket(on_message, on_qrcode, on_connection)
        
        # Connect and keep alive
        websocket_manager.connect()
        logger.info("Document Scanner service started successfully")
        
        try:
            # Keep the service running
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Shutting down...")
        finally:
            if websocket_manager.is_connected():
                websocket_manager.disconnect()
                logger.info("WebSocket disconnected")
    
    except Exception as e:
        logger.error(f"Failed to start Document Scanner service: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
