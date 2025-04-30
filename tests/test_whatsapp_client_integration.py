"""
Integration tests for the WhatsAppClient class.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from app.whatsapp_client import WhatsAppClient
from config.settings import EVOLUTION_API_URL, EVOLUTION_API_KEY, DOWNLOAD_BASE_DIR


@pytest.fixture
def mock_evolution_api():
    """Create a mock for the evolutionapi client."""
    mock_client = MagicMock()
    
    # Mock responses for various methods
    mock_client.send_text.return_value = {"key": {"id": "test_message_id"}}
    mock_client.send_media.return_value = {"key": {"id": "test_media_id"}}
    mock_client.get_qr_code.return_value = {"qrcode": "test_qr_code"}
    mock_client.request_code.return_value = {"code": "test_code"}
    
    return mock_client


@pytest.fixture
def whatsapp_client(mock_evolution_api):
    """Create a WhatsAppClient with a mocked evolution_api."""
    with patch("app.whatsapp_client.EvolutionClient", return_value=mock_evolution_api):
        client = WhatsAppClient(EVOLUTION_API_URL, EVOLUTION_API_KEY)
        yield client


class TestWhatsAppClientIntegration:
    """Integration tests for the WhatsAppClient class."""
    
    def test_initialization(self, whatsapp_client, mock_evolution_api):
        """Test that the client initializes correctly."""
        assert whatsapp_client.api_url == EVOLUTION_API_URL
        assert whatsapp_client.api_key == EVOLUTION_API_KEY
        assert whatsapp_client.client == mock_evolution_api
    
    def test_send_text(self, whatsapp_client, mock_evolution_api):
        """Test sending a text message."""
        test_jid = "test_user@test.com"
        test_message = "Hello, World!"
        
        result = whatsapp_client.send_text(test_jid, test_message)
        
        assert result is True
        mock_evolution_api.send_text.assert_called_once_with(test_jid, test_message)
    
    def test_send_text_error_handling(self, whatsapp_client, mock_evolution_api):
        """Test error handling when sending a text message fails."""
        mock_evolution_api.send_text.side_effect = Exception("Test error")
        
        test_jid = "test_user@test.com"
        test_message = "Hello, World!"
        
        result = whatsapp_client.send_text(test_jid, test_message)
        
        assert result is False
        mock_evolution_api.send_text.assert_called_once_with(test_jid, test_message)
    
    def test_send_media(self, whatsapp_client, mock_evolution_api):
        """Test sending a media file."""
        test_jid = "test_user@test.com"
        
        # Create a test file to send
        test_file = os.path.join(DOWNLOAD_BASE_DIR, "test_file.txt")
        os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, "w") as f:
            f.write("Test file content")
        
        try:
            result, message_id = whatsapp_client.send_media(test_jid, test_file)
            
            assert result is True
            assert message_id == "test_media_id"
            mock_evolution_api.send_media.assert_called_once()
            
            # Check that the correct parameters were passed
            call_args = mock_evolution_api.send_media.call_args[0]
            assert call_args[0] == test_jid
            
        finally:
            # Clean up test file
            if os.path.exists(test_file):
                os.unlink(test_file)
    
    def test_send_media_error_handling(self, whatsapp_client, mock_evolution_api):
        """Test error handling when sending a media file fails."""
        mock_evolution_api.send_media.side_effect = Exception("Test error")
        
        test_jid = "test_user@test.com"
        test_file = "/non/existent/file.txt"  # Non-existent file
        
        result, message_id = whatsapp_client.send_media(test_jid, test_file)
        
        assert result is False
        assert message_id is None
    
    def test_check_connection(self, whatsapp_client, mock_evolution_api):
        """Test checking connection status."""
        # Mock a connected state
        mock_evolution_api.get_connection_status.return_value = {"state": "open"}
        
        result = whatsapp_client.check_connection()
        
        assert result is True
        mock_evolution_api.get_connection_status.assert_called_once()
    
    def test_check_connection_not_connected(self, whatsapp_client, mock_evolution_api):
        """Test checking connection status when not connected."""
        # Mock a disconnected state
        mock_evolution_api.get_connection_status.return_value = {"state": "close"}
        
        result = whatsapp_client.check_connection()
        
        assert result is False
        mock_evolution_api.get_connection_status.assert_called_once()
    
    def test_check_connection_error(self, whatsapp_client, mock_evolution_api):
        """Test error handling when checking connection fails."""
        mock_evolution_api.get_connection_status.side_effect = Exception("Test error")
        
        result = whatsapp_client.check_connection()
        
        assert result is False
        mock_evolution_api.get_connection_status.assert_called_once()

    def test_setup_webhook(self, whatsapp_client, mock_evolution_api):
        """Test setting up webhook."""
        test_webhook_url = "https://example.com/webhook"
        
        with patch.object(whatsapp_client, 'client') as mock_client:
            mock_client.set_webhook.return_value = {"status": "success"}
            
            result = whatsapp_client.setup_webhook(test_webhook_url)
            
            assert result is True
            mock_client.set_webhook.assert_called_once_with(test_webhook_url)
    
    def test_setup_webhook_error(self, whatsapp_client, mock_evolution_api):
        """Test error handling when setting up webhook fails."""
        test_webhook_url = "https://example.com/webhook"
        
        with patch.object(whatsapp_client, 'client') as mock_client:
            mock_client.set_webhook.side_effect = Exception("Test error")
            
            result = whatsapp_client.setup_webhook(test_webhook_url)
            
            assert result is False
            mock_client.set_webhook.assert_called_once_with(test_webhook_url)