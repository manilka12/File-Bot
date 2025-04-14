"""
WhatsApp client module for handling messaging through the EvolutionAPI.
"""

import io
import os
import logging
import mimetypes
from evolutionapi.client import EvolutionClient
from evolutionapi.models.message import TextMessage, MediaMessage

from config.settings import BASE_URL, API_TOKEN, INSTANCE_ID, INSTANCE_TOKEN

# Initialize logger
logger = logging.getLogger(__name__)

class WhatsAppClient:
    """Client for interacting with WhatsApp through EvolutionAPI."""
    
    def __init__(self):
        """Initialize the WhatsApp client with EvolutionAPI."""
        logger.info("Initializing Evolution API client...")
        try:
            self.client = EvolutionClient(
                base_url=BASE_URL,
                api_token=API_TOKEN
            )
            logger.info("WhatsApp client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize client: {str(e)}")
            raise
    
    def send_text(self, recipient_jid, text_content):
        """
        Sends a text message.
        
        Args:
            recipient_jid (str): The recipient's JID
            text_content (str): The message text
            
        Returns:
            bool: True if successful, False if failed
        """
        try:
            message = TextMessage(number=recipient_jid, text=text_content)
            self.client.messages.send_text(INSTANCE_ID, message, INSTANCE_TOKEN)
            return True
        except Exception as e:
            logger.error(f"Text message failed: {str(e)}")
            return False
    
    def send_media(self, recipient_jid, file_path, caption=""):
        """
        Sends a media file using binary stream approach.
        
        Args:
            recipient_jid (str): The recipient's JID
            file_path (str): Path to the media file
            caption (str): Optional caption for the media
            
        Returns:
            tuple: (response, message_id) - API response and message ID if successful
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None, None

            mimetype = mimetypes.guess_type(file_path)[0] or 'application/pdf'
            filename = os.path.basename(file_path)
            
            logger.info(f"Sending {filename} to {recipient_jid}")

            media_message = MediaMessage(
                number=recipient_jid,
                mediatype='document',
                mimetype=mimetype,
                fileName=filename,
                caption=caption
            )

            with open(file_path, 'rb') as binary_file:
                binary_stream = io.BytesIO(binary_file.read())
                response = self.client.messages.send_media(
                    instance_id=INSTANCE_ID,
                    message=media_message,
                    instance_token=INSTANCE_TOKEN,
                    file=binary_stream
                )

                # Only log essential response info, not the full response
                if (response and isinstance(response, dict) and 
                    'key' in response and isinstance(response['key'], dict)):
                    sent_message_id = response['key'].get('id')
                    if sent_message_id:
                        logger.info(f"Successfully sent {filename} (ID: {sent_message_id})")
                        return response, sent_message_id
                
                logger.error("Failed to send media - invalid response format")
                return response, None

        except Exception as e:
            logger.error(f"Error sending {filename}: {str(e)}")
            return None, None
    
    def create_websocket(self, on_message, on_qrcode=None, on_connection=None):
        """
        Creates and configures a WebSocket for real-time messaging.
        
        Args:
            on_message (function): Callback for message events
            on_qrcode (function): Callback for QR code events
            on_connection (function): Callback for connection events
            
        Returns:
            websocket_manager: The configured WebSocket manager
        """
        from evolutionapi.models.websocket import WebSocketConfig
        
        try:
            websocket_config = WebSocketConfig(
                enabled=True, 
                events=["MESSAGES_UPSERT", "CONNECTION_UPDATE", "QRCODE_UPDATED"]
            )
            
            self.client.websocket.set_websocket(
                INSTANCE_ID, 
                websocket_config, 
                INSTANCE_TOKEN
            )
            
            websocket_manager = self.client.create_websocket(
                instance_id=INSTANCE_ID, 
                api_token=INSTANCE_TOKEN, 
                max_retries=5, 
                retry_delay=10.0
            )
            
            websocket_manager.on('messages.upsert', on_message)
            
            if on_qrcode:
                websocket_manager.on('qrcode.updated', on_qrcode)
                
            if on_connection:
                websocket_manager.on('connection.update', on_connection)
                
            return websocket_manager
            
        except Exception as e:
            logger.error(f"Error creating WebSocket: {str(e)}")
            raise
