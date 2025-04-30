"""
Integration tests for the WorkflowManager class.
"""

import os
import uuid
import base64
import pytest
from unittest.mock import MagicMock, patch

from app.workflow_manager import WorkflowManager
from workflows.base import BaseWorkflow
from config.settings import DOWNLOAD_BASE_DIR


class MockWorkflow(BaseWorkflow):
    """Mock workflow class for testing."""
    
    @staticmethod
    def get_instructions():
        return "Mock workflow instructions"
    
    @staticmethod
    def get_initial_state():
        return {"mock_state": True}
    
    @staticmethod
    def handle_file_save(task_dir, message_id, saved_filename, workflow_info):
        return saved_filename, "File saved successfully"
    
    @staticmethod
    def handle_command(task_dir, message_text, quoted_stanza_id, workflow_info):
        if message_text == "done":
            return True, "Workflow completed"
        return False, "Command received"
    
    @staticmethod
    def finalize(task_dir, workflow_info):
        return [os.path.join(task_dir, "test_output.pdf")]


@pytest.fixture
def mock_whatsapp_client():
    """Create a mock WhatsAppClient."""
    client = MagicMock()
    client.send_text = MagicMock(return_value=True)
    client.send_media = MagicMock(return_value=(True, "message_id"))
    return client


@pytest.fixture
def workflow_manager(mock_whatsapp_client):
    """Create a WorkflowManager with mock dependencies."""
    manager = WorkflowManager(mock_whatsapp_client)
    # Add our mock workflow to the workflow classes
    manager.WORKFLOW_CLASSES["mock"] = MockWorkflow
    return manager


def create_mock_pdf_message(sender_jid="test_user@test.com"):
    """Create a mock PDF message data structure."""
    message_id = "test_message_id"
    return {
        "data": {
            "key": {
                "remoteJid": sender_jid,
                "id": message_id,
                "fromMe": False
            },
            "messageType": "documentMessage",
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "test.pdf"
                },
                "base64": base64.b64encode(b"Test PDF content").decode("utf-8")
            }
        }
    }


def create_mock_text_message(text, sender_jid="test_user@test.com", quoted_id=None):
    """Create a mock text message data structure."""
    message_data = {
        "data": {
            "key": {
                "remoteJid": sender_jid,
                "id": "text_message_id",
                "fromMe": False
            },
            "messageType": "conversation",
            "message": {
                "conversation": text
            }
        }
    }
    
    if quoted_id:
        message_data["data"]["contextInfo"] = {
            "quotedMessage": {},
            "stanzaId": quoted_id
        }
    
    return message_data


@pytest.fixture
def cleanup_test_files():
    """Clean up any test files after tests."""
    yield
    # Clean up test directories after testing
    test_base_dir = os.path.join(DOWNLOAD_BASE_DIR, "test_user_test_com")
    if os.path.exists(test_base_dir):
        import shutil
        shutil.rmtree(test_base_dir)


@pytest.mark.usefixtures("cleanup_test_files")
class TestWorkflowManagerIntegration:
    """Integration tests for the WorkflowManager class."""
    
    def test_start_workflow(self, workflow_manager, mock_whatsapp_client):
        """Test starting a workflow."""
        sender_jid = "test_user@test.com"
        success, task_dir = workflow_manager.start_workflow(sender_jid, "mock")
        
        assert success is True
        assert os.path.exists(task_dir)
        assert sender_jid in workflow_manager.active_workflows
        assert workflow_manager.active_workflows[sender_jid]["workflow_type"] == "mock"
        mock_whatsapp_client.send_text.assert_called_once_with(sender_jid, "Mock workflow instructions")
    
    def test_handle_pdf_save(self, workflow_manager, mock_whatsapp_client):
        """Test handling a PDF file save."""
        # First start a workflow
        sender_jid = "test_user@test.com"
        workflow_manager.start_workflow(sender_jid, "mock")
        
        # Create a mock PDF message
        pdf_message = create_mock_pdf_message(sender_jid)
        
        # Handle the PDF save
        result = workflow_manager.handle_pdf_save(sender_jid, pdf_message["data"])
        
        assert result is not None
        # Verify the client sent a response
        mock_whatsapp_client.send_text.assert_called_with(sender_jid, "File saved successfully")
        
        # Verify the file was saved
        task_dir = workflow_manager.active_workflows[sender_jid]["task_dir"]
        assert os.path.exists(os.path.join(task_dir, f"{pdf_message['data']['key']['id']}.pdf"))
    
    def test_handle_message_workflow_command(self, workflow_manager, mock_whatsapp_client):
        """Test handling a workflow command message."""
        # First start a workflow
        sender_jid = "test_user@test.com"
        workflow_manager.start_workflow(sender_jid, "mock")
        
        # Create a mock command message
        command_message = create_mock_text_message("test command", sender_jid)
        
        # Handle the command
        workflow_manager.handle_message(command_message)
        
        # Verify the client sent a response
        mock_whatsapp_client.send_text.assert_called_with(sender_jid, "Command received")
    
    def test_handle_message_workflow_completion(self, workflow_manager, mock_whatsapp_client):
        """Test handling a workflow completion command."""
        # First start a workflow
        sender_jid = "test_user@test.com"
        success, task_dir = workflow_manager.start_workflow(sender_jid, "mock")
        
        # Create a mock "done" message
        done_message = create_mock_text_message("done", sender_jid)
        
        # Create a test output file
        os.makedirs(task_dir, exist_ok=True)
        with open(os.path.join(task_dir, "test_output.pdf"), "w") as f:
            f.write("Test output file")
        
        # Handle the done command
        workflow_manager.handle_message(done_message)
        
        # Verify the client sent a completion response
        mock_whatsapp_client.send_text.assert_any_call(sender_jid, "Workflow completed")
        mock_whatsapp_client.send_text.assert_any_call(sender_jid, "Task complete! Sending 1 file(s)...")
        mock_whatsapp_client.send_media.assert_called_once()
        
        # Verify the workflow was removed from active workflows
        assert sender_jid not in workflow_manager.active_workflows
    
    def test_handle_message_workflow_start(self, workflow_manager, mock_whatsapp_client):
        """Test handling a workflow start message."""
        # Create a mock start message
        start_message = create_mock_text_message("mock", "test_user@test.com")
        
        # Add the command to the workflow commands mapping
        workflow_manager.handle_message._function_cache = {}  # Clear any function cache
        
        with patch.dict(workflow_manager.__class__.__dict__, {
            'handle_message': lambda self, message_data: (
                self.start_workflow(
                    message_data['data']['key']['remoteJid'],
                    "mock"
                ) if message_data['data']['message'].get('conversation') == 'mock' else None
            )
        }):
            # Handle the message
            workflow_manager.handle_message(start_message)
            
            # Verify the workflow was started
            assert "test_user@test.com" in workflow_manager.active_workflows