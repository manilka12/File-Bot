"""
Workflow for converting markdown text messages to PDF.
First tries md-to-pdf (ARM compatible), then falls back to md2pdf or pandoc.
"""

import os
import logging
import tempfile
import json
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

from workflows.base import BaseWorkflow
from utils.logging_utils import setup_logger
from app.tasks import markdown_to_pdf_task, execute_task

# Initialize logger with enhanced logging
logger = setup_logger(__name__)

class MarkdownToPdfWorkflow(BaseWorkflow):
    """Handles markdown text to PDF conversion with fallback mechanisms."""
    
    @classmethod
    def get_instructions(cls) -> str:
        """
        Get the user instructions for this workflow.
        
        Returns:
            str: User instructions
        """
        return ("Started Markdown to PDF conversion.\n"
                "Send me markdown text messages, and I'll convert them into a PDF document.\n"
                "You can send multiple messages - they will be combined in order.\n"
                "Type 'done' when you've sent all your markdown text to generate the PDF.")
    
    @classmethod
    def get_initial_state(cls) -> Dict[str, Any]:
        """
        Get the initial state for this workflow.
        
        Returns:
            dict: Initial workflow state
        """
        return {
            "markdown_content": [],
            "message_ids": [],
            "task_id": None,  # Track Celery task ID for markdown-to-PDF conversion
            "task_status": None  # Track task status
        }
    
    def handle_command(self, message_text: str, quoted_stanza_id: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Handle workflow commands.
        
        Args:
            message_text: Message text (command)
            quoted_stanza_id: ID of the quoted message (if any)
            
        Returns:
            Tuple[bool, Optional[str]]: (is_done, message)
        """
        command = message_text.lower()
        
        # Check for status command
        if command == "status":
            return self._check_task_status()
        
        # Handle 'done' command to finalize markdown conversion
        if command == "done":
            if not self.state.get("markdown_content"):
                return False, "No markdown content received yet. Please send some markdown text before finishing."
                
            return self._start_conversion_task()
        
        # If not a command, treat as markdown content
        success, message = self._append_markdown_content(
            f"cmd_{len(self.state.get('message_ids', [])) + 1}", 
            message_text
        )
        
        return False, message
    
    def handle_file_save(self, message_id: str, saved_filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        This workflow doesn't handle files directly, but we need to implement this method.
        
        Args:
            message_id: Message ID of the received file
            saved_filename: Filename for the saved file
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (filename, message)
        """
        # Not expected to be called for this workflow
        return saved_filename, "This workflow handles text messages, not files. Please send markdown text directly."
    
    def finalize(self) -> List[str]:
        """
        Finalize the workflow and return the output files.
        
        Returns:
            List[str]: List of output file paths
        """
        # Wait for any pending task to complete
        self._wait_for_pending_task()
        
        # If we have a PDF from the task, return it
        if self.state.get("output_pdf") and os.path.exists(self.state.get("output_pdf")):
            return [self.state.get("output_pdf")]
        
        # If no task result or task failed, try to generate PDF synchronously
        result = self._generate_pdf_from_messages()
        
        if result.get("success") and "path" in result:
            return [result["path"]]
        else:
            logger.error(f"Failed to generate PDF: {result.get('error', 'Unknown error')}")
            return []
    
    def _append_markdown_content(self, message_id: str, text_content: str) -> Tuple[bool, str]:
        """
        Appends markdown content to the collection.
        
        Args:
            message_id: Message ID
            text_content: Markdown text content
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        # Initialize markdown content if not already present
        if "markdown_content" not in self.state:
            self.state["markdown_content"] = []
            self.state["message_ids"] = []
            
        # Add new content
        self.state["markdown_content"].append(text_content)
        self.state["message_ids"].append(message_id)
        
        # Create a message to acknowledge receipt
        msg_count = len(self.state["markdown_content"])
        return True, f"Markdown content received ({msg_count} message{'s' if msg_count > 1 else ''}). Send more markdown text or 'done' to generate PDF."
    
    def _start_conversion_task(self) -> Tuple[bool, str]:
        """
        Start the markdown to PDF conversion task asynchronously.
        
        Returns:
            Tuple[bool, str]: (is_done, message)
        """
        if not self.state.get("markdown_content"):
            return False, "No markdown content to convert."
        
        # Combine all markdown content with proper spacing
        combined_content = "\n\n".join(self.state["markdown_content"])
        
        # Generate timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"document_{timestamp}.pdf"
        output_path = os.path.join(self.task_dir, output_filename)
        
        # Start the conversion task
        logger.info(f"Starting markdown to PDF conversion task")
        task_result = execute_task(markdown_to_pdf_task, combined_content, output_path, title="Markdown Document")
        
        # Store task info for tracking
        if hasattr(task_result, 'id'):  # It's an async task
            self.state['task_id'] = task_result.id
            self.state['task_status'] = 'PENDING'
            
            return False, (
                "Converting your markdown text to PDF in the background.\n"
                "This may take a moment.\n"
                "Type 'status' to check progress or 'done' again to finish."
            )
        else:
            # Task executed synchronously, process the result now
            result = task_result
            
            if result.get("success") and "path" in result and os.path.exists(result["path"]):
                self.state["output_pdf"] = result["path"]
                self.state['task_status'] = 'COMPLETED'
                
                return True, "Markdown text converted to PDF successfully."
            else:
                error_msg = result.get("error", "Unknown error")
                return False, f"Failed to convert markdown to PDF: {error_msg}"
    
    def _check_task_status(self) -> Tuple[bool, str]:
        """
        Check the status of the conversion task.
        
        Returns:
            tuple: (is_done, message)
        """
        if not self.state.get("task_id"):
            return False, "No conversion task in progress. Send markdown text and type 'done' to start conversion."
        
        try:
            # Import needed Celery components here to avoid circular imports
            from celery.result import AsyncResult
            from app.celery_app import app
        except ImportError:
            return False, "Task status checking not available (Celery not configured)"
        
        task_id = self.state["task_id"]
        
        try:
            # Get the task result object
            task_result = AsyncResult(task_id, app=app)
            
            # Update the task status
            status = task_result.status
            self.state["task_status"] = status
            
            if status in ['PENDING', 'STARTED', 'RETRY']:
                return False, f"Conversion task is in progress: {status}"
            elif status == 'SUCCESS':
                # If task is complete but result not handled yet, handle it now
                if not self.state.get("output_pdf"):
                    try:
                        # Get task result
                        result = task_result.get(timeout=10)
                        
                        if result.get("success") and "path" in result and os.path.exists(result["path"]):
                            self.state["output_pdf"] = result["path"]
                            
                            logger.info(f"Updated status for completed conversion task")
                            return False, "Conversion complete! Type 'done' to finish and receive your PDF."
                        else:
                            error_msg = result.get("error", "Unknown error")
                            logger.error(f"Task completed but conversion failed: {error_msg}")
                            return False, f"Conversion task completed but failed: {error_msg}"
                    except Exception as e:
                        logger.error(f"Error handling completed task result: {str(e)}")
                        return False, f"Error processing conversion task result: {str(e)}"
                
                return False, "Markdown conversion complete! Type 'done' to finish and receive your PDF."
            elif status == 'FAILURE':
                return False, "Markdown conversion task failed. Please try again."
            else:
                return False, f"Conversion task status: {status}"
                
        except Exception as e:
            logger.error(f"Error checking task status: {str(e)}")
            return False, f"Error checking conversion task status: {str(e)}"
    
    def _wait_for_pending_task(self) -> None:
        """
        Wait for pending conversion task to complete before finalizing.
        """
        if not self.state.get("task_id"):
            return
        
        try:
            # Import needed Celery components
            from celery.result import AsyncResult
            from app.celery_app import app
        except ImportError:
            logger.warning("Celery not available, skipping task waiting")
            return
        
        logger.info("Checking for pending conversion task before finalizing")
        
        task_id = self.state["task_id"]
        
        try:
            # Get the task result
            task_result = AsyncResult(task_id, app=app)
            
            # If task is ready, get the result
            if task_result.ready():
                logger.info(f"Processing completed conversion task {task_id}")
                
                try:
                    # Get task result with a short timeout
                    result = task_result.get(timeout=30)
                    
                    # If conversion was successful, set the output PDF path
                    if result.get("success") and "path" in result and os.path.exists(result["path"]):
                        self.state["output_pdf"] = result["path"]
                        logger.info("Updated output PDF path during finalization")
                    else:
                        error_msg = result.get("error", "Unknown error")
                        logger.error(f"Task completed but conversion failed: {error_msg}")
                except Exception as e:
                    logger.error(f"Error processing completed task result during finalization: {str(e)}")
            else:
                # For incomplete task, try to wait a short time
                logger.info(f"Waiting for conversion task {task_id} to complete")
                try:
                    # Wait with timeout
                    result = task_result.get(timeout=60)  # 1 minute timeout
                    
                    # If conversion was successful, set the output PDF path
                    if result.get("success") and "path" in result and os.path.exists(result["path"]):
                        self.state["output_pdf"] = result["path"]
                        logger.info("Updated output PDF path after waiting")
                    else:
                        error_msg = result.get("error", "Unknown error")
                        logger.error(f"Task completed but conversion failed after waiting: {error_msg}")
                except Exception as e:
                    logger.error(f"Conversion task {task_id} did not complete within timeout or failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error checking conversion task {task_id} status: {str(e)}")
    
    def _generate_pdf_from_messages(self) -> Dict[str, Any]:
        """
        Generate a PDF from collected markdown messages.
        Fallback method when asynchronous task fails or isn't available.
        
        Returns:
            Dict[str, Any]: Result information
        """
        if "markdown_content" not in self.state or not self.state["markdown_content"]:
            return {
                "success": False,
                "error": "No markdown content available"
            }
            
        # Combine all markdown content with proper spacing
        combined_content = "\n\n".join(self.state["markdown_content"])
        
        # Generate timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"document_{timestamp}.pdf"
        output_path = os.path.join(self.task_dir, output_filename)
        
        # Try to execute the task synchronously
        try:
            task_result = execute_task(markdown_to_pdf_task, combined_content, output_path, title="Markdown Document")
            
            # If it's an AsyncResult, we need to wait for it
            if hasattr(task_result, 'get'):
                result = task_result.get(timeout=60)  # 1 minute timeout
            else:
                result = task_result
                
            return result
        except Exception as e:
            logger.error(f"Error in markdown to PDF conversion: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }