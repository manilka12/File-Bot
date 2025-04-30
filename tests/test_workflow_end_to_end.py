"""
End-to-end integration tests for the workflow processing pipeline.
"""

import os
import base64
import shutil
import pytest
from unittest.mock import MagicMock, patch

from app.workflow_manager import WorkflowManager
from workflows.split_workflow import SplitWorkflow
from config.settings import DOWNLOAD_BASE_DIR


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
    return WorkflowManager(mock_whatsapp_client)


@pytest.fixture
def test_pdf_content():
    """Create test PDF content."""
    # This is a minimal valid PDF file content
    return b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 100 100]>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF"


@pytest.fixture
def setup_test_environment():
    """Set up test environment and clean up after tests."""
    # Create test directories if needed
    yield
    
    # Clean up test directories
    test_dir = os.path.join(DOWNLOAD_BASE_DIR, "test_user_s_whatsapp_net")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


def create_mock_pdf_message(test_pdf_content, message_id="test_pdf_id", sender_jid="test_user@s.whatsapp.net"):
    """Create a mock PDF message with the given content."""
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
                "base64": base64.b64encode(test_pdf_content).decode("utf-8")
            }
        }
    }


def create_mock_text_message(text, sender_jid="test_user@s.whatsapp.net", quoted_id=None):
    """Create a mock text message."""
    message = {
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
        message["data"]["contextInfo"] = {
            "quotedMessage": {},
            "stanzaId": quoted_id
        }
    
    return message


@pytest.mark.usefixtures("setup_test_environment")
class TestWorkflowEndToEnd:
    """End-to-end tests for the workflow processing pipeline."""

    def test_split_workflow_end_to_end(self, workflow_manager, mock_whatsapp_client, test_pdf_content):
        """
        Test the end-to-end flow of the split workflow.
        
        This test simulates:
        1. User sending a "split pdf" command
        2. User uploading a PDF
        3. User replying to the PDF with page ranges
        4. System processing the split and returning the result
        """
        sender_jid = "test_user@s.whatsapp.net"
        
        # Mock the PDF reader to avoid actually parsing the PDF
        with patch("pypdf.PdfReader") as mock_pdf_reader:
            # Configure the mock to return proper page information
            mock_reader_instance = MagicMock()
            mock_reader_instance.pages = [MagicMock()] * 10  # Mock 10 pages
            mock_pdf_reader.return_value = mock_reader_instance
            
            # 1. Start the split workflow
            start_message = create_mock_text_message("split pdf", sender_jid)
            workflow_manager.handle_message(start_message)
            
            # Verify workflow was started
            assert sender_jid in workflow_manager.active_workflows
            assert workflow_manager.active_workflows[sender_jid]["workflow_type"] == "split"
            mock_whatsapp_client.send_text.assert_called_with(sender_jid, SplitWorkflow.get_instructions())
            
            # 2. Send a PDF document
            pdf_message = create_mock_pdf_message(test_pdf_content, "pdf_message_id", sender_jid)
            workflow_manager.handle_message(pdf_message)
            
            # Verify PDF was saved
            task_dir = workflow_manager.active_workflows[sender_jid]["task_dir"]
            pdf_path = os.path.join(task_dir, "pdf_message_id.pdf")
            assert os.path.exists(pdf_path)
            
            # Verify appropriate message was sent to user
            mock_whatsapp_client.send_text.assert_called_with(
                sender_jid, 
                "PDF received. Reply to it with page ranges (e.g., '1-10, 15, 20-25')"
            )
            
            # 3. Send page ranges as reply to the PDF
            with patch.object(SplitWorkflow, "finalize") as mock_finalize:
                # Mock the finalize method to return test output files
                output_file_1 = os.path.join(task_dir, "test_output_1-5.pdf")
                output_file_2 = os.path.join(task_dir, "test_output_6-10.pdf")
                
                # Create test output files
                for file in [output_file_1, output_file_2]:
                    with open(file, "wb") as f:
                        f.write(test_pdf_content)
                
                mock_finalize.return_value = [output_file_1, output_file_2]
                
                # Send a command with page ranges
                range_message = create_mock_text_message("1-5, 6-10", sender_jid, quoted_id="pdf_message_id")
                workflow_manager.handle_message(range_message)
                
                # Verify finalization was called with correct parameters
                mock_finalize.assert_called_once()
                
                # Verify that the result files were sent to the user
                assert mock_whatsapp_client.send_text.call_args_list[-2][0][1] == "Task complete! Sending 2 file(s)..."
                assert mock_whatsapp_client.send_media.call_count == 2
                assert mock_whatsapp_client.send_text.call_args_list[-1][0][1] == "All files sent successfully."
                
                # Verify workflow was removed from active workflows
                assert sender_jid not in workflow_manager.active_workflows