"""
PDF Merge workflow handler for the Document Scanner application.
"""

import os
import logging
import json
from pypdf import PdfWriter

from utils.file_utils import read_order_file, write_order_file, check_file_exists_and_complete
from utils.logging_utils import setup_logger
from workflows.base import BaseWorkflow
from app.tasks import merge_pdfs_task, execute_task

# Set up logger
logger = setup_logger(__name__)

class MergeWorkflow(BaseWorkflow):
    """Handles the PDF merge workflow."""
    
    @classmethod
    def get_instructions(cls) -> str:
        """
        Get the user instructions for this workflow.
        
        Returns:
            str: User instructions
        """
        return ("Started PDF Merge.\n"
                "Send me the PDF files you want to merge. They will be merged in the order they're received.\n"
                "To change the order of a PDF, reply to it with a number (e.g., '1', '2', etc.).\n"
                "Type 'done' when you've sent all files to merge.")
    
    @classmethod
    def get_initial_state(cls) -> dict:
        """
        Get the initial state for this workflow.
        
        Returns:
            dict: Initial workflow state
        """
        return {
            "pdf_files": {},  # Will store {message_id: filename} pairs
            "original_filenames": {},
            "task_id": None,  # Track Celery task ID for merge operation
            "task_status": None  # Track task status
        }
    
    def handle_file_save(self, message_id: str, saved_filename: str) -> tuple:
        """
        Handles saving a PDF to the merge workflow's task directory.
        
        Args:
            message_id: Message ID of the received PDF
            saved_filename: Filename for the saved PDF
            
        Returns:
            tuple: (saved_filename, message) - Filename and message to send
        """
        # Store the original filename using common method
        self.store_original_filename(message_id, saved_filename)
        
        # Store PDF filename in state
        self.state["pdf_files"][message_id] = saved_filename
        
        # Process the saved PDF
        order_data = read_order_file(self.task_dir)
        next_order = max(list(order_data.values()) + [0]) + 1
        order_data[saved_filename] = next_order
        write_order_file(self.task_dir, order_data)
        
        logger.info(f"Saved PDF {saved_filename} (order: {next_order})")
        
        return saved_filename, f"PDF #{next_order} received. Send more PDFs, change order by replying with a number, or type 'done' to merge."
    
    def handle_command(self, message_text: str, quoted_stanza_id: str) -> tuple:
        """
        Handle workflow commands.
        
        Args:
            message_text: Message text (command)
            quoted_stanza_id: ID of the quoted message (if any)
            
        Returns:
            tuple: (is_done, message) - Whether the workflow is done and a message to send
        """
        # Check for status command
        if message_text.lower() == "status":
            return self._check_task_status()
        
        # Handle 'done' command
        if message_text.lower() == "done":
            # Check if we have any PDFs to merge
            order_data = read_order_file(self.task_dir)
            if not order_data:
                return False, "No PDFs received yet. Please send at least one PDF before finishing."
            
            # Start the merge task asynchronously
            return self._start_merge_task(order_data)
        
        # Check if it's a reorder command (number reply to PDF)
        if quoted_stanza_id and message_text.strip().isdigit():
            # Find the filename corresponding to the quoted message
            target_filename = None
            for msg_id, filename in self.state.get("pdf_files", {}).items():
                if msg_id == quoted_stanza_id:
                    target_filename = filename
                    break
            
            if target_filename:
                # Handle reordering
                success, message = self._handle_order_override(target_filename, message_text)
                return False, message  # Return false to keep the workflow going
            else:
                return False, "Could not find the PDF you're trying to reorder."
        
        # Any other command
        return False, "Send PDFs to merge, reply to a PDF with a number to change its order, or type 'done' to finish."
    
    def finalize(self) -> list:
        """
        Finalize the workflow and return the output files.
        
        Returns:
            list: List of output file paths
        """
        # Wait for any pending merge task to complete
        self._wait_for_pending_task()
        
        # If we have a merged file from the task, return it
        if self.state.get("merged_file") and os.path.exists(self.state["merged_file"]):
            return [self.state["merged_file"]]
        
        # If no task result is available, try to merge synchronously
        order_data = read_order_file(self.task_dir)
        if not order_data:
            logger.warning("No PDFs to merge")
            return []
        
        # Merge the PDFs in order
        merged_pdf_path, missing_files = self._merge_pdfs_in_order(order_data)
        
        if merged_pdf_path and os.path.exists(merged_pdf_path):
            return [merged_pdf_path]
        else:
            if missing_files:
                logger.error(f"Could not merge PDFs, missing: {', '.join(missing_files)}")
            else:
                logger.error("Failed to create merged PDF")
            return []
    
    def _start_merge_task(self, order_data: dict) -> tuple:
        """
        Start the merge task asynchronously.
        
        Args:
            order_data: Dictionary mapping filenames to their order
            
        Returns:
            tuple: (is_done, message)
        """
        # Sort files by order
        sorted_files = sorted(order_data.items(), key=lambda item: item[1])
        input_files = []
        
        for filename, _ in sorted_files:
            file_path = os.path.join(self.task_dir, filename)
            if os.path.exists(file_path):
                input_files.append(file_path)
        
        if not input_files:
            return False, "No valid PDF files to merge."
        
        # Define output path
        output_filename = "Merged_pdf.pdf"
        output_path = os.path.join(self.task_dir, output_filename)
        
        # Start the merge task
        logger.info(f"Starting merge task with {len(input_files)} PDFs")
        task_result = execute_task(merge_pdfs_task, input_files, output_path)
        
        # Store task info for tracking
        if hasattr(task_result, 'id'):  # It's an async task
            self.state['task_id'] = task_result.id
            self.state['task_status'] = 'PENDING'
            
            return False, (
                f"Starting PDF merge in the background with {len(input_files)} files.\n"
                f"This may take a moment for large files.\n"
                f"Type 'status' to check progress or 'done' again when ready to finish."
            )
        else:
            # Task executed synchronously, process the result now
            success = task_result
            
            if success and os.path.exists(output_path):
                self.state["merged_file"] = output_path
                self.state['task_status'] = 'COMPLETED'
                
                return True, f"Successfully merged {len(input_files)} PDFs."
            else:
                return False, "Failed to merge PDFs. Please try again."
    
    def _check_task_status(self) -> tuple:
        """
        Check the status of the merge task.
        
        Returns:
            tuple: (is_done, message)
        """
        if not self.state.get("task_id"):
            return False, "No merge task in progress. Send PDFs and type 'done' to start merging."
        
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
                return False, f"Merge task is in progress: {status}"
            elif status == 'SUCCESS':
                # If task is complete but result not handled yet, handle it now
                if not self.state.get("merged_file"):
                    try:
                        # Get task result
                        result = task_result.get(timeout=10)
                        
                        output_path = os.path.join(self.task_dir, "Merged_pdf.pdf")
                        if result and os.path.exists(output_path):
                            self.state["merged_file"] = output_path
                            
                            logger.info(f"Updated status for completed merge task")
                            return False, "PDF merge complete! Type 'done' to finish and receive the merged PDF."
                        else:
                            logger.error(f"Task completed but merge failed")
                            return False, "Merge task completed but failed to create merged PDF."
                    except Exception as e:
                        logger.error(f"Error handling completed task result: {str(e)}")
                        return False, f"Error processing merge task result: {str(e)}"
                
                return False, "PDF merge complete! Type 'done' to finish and receive the merged PDF."
            elif status == 'FAILURE':
                return False, "PDF merge task failed. Please try again or send new files."
            else:
                return False, f"Merge task status: {status}"
                
        except Exception as e:
            logger.error(f"Error checking task status: {str(e)}")
            return False, f"Error checking merge task status: {str(e)}"
    
    def _wait_for_pending_task(self) -> None:
        """
        Wait for pending merge task to complete before finalizing.
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
        
        logger.info("Checking for pending merge task before finalizing")
        
        task_id = self.state["task_id"]
        
        try:
            # Get the task result
            task_result = AsyncResult(task_id, app=app)
            
            # If task is ready, get the result
            if task_result.ready():
                logger.info(f"Processing completed merge task {task_id}")
                
                try:
                    # Get task result with a short timeout
                    result = task_result.get(timeout=30)
                    
                    # If merge was successful, set the merged file path
                    output_path = os.path.join(self.task_dir, "Merged_pdf.pdf")
                    if result and os.path.exists(output_path):
                        self.state["merged_file"] = output_path
                        logger.info("Updated merged file path during finalization")
                    else:
                        logger.error("Task completed but merge failed")
                except Exception as e:
                    logger.error(f"Error processing completed merge task during finalization: {str(e)}")
            else:
                # For incomplete task, try to wait a short time
                logger.info(f"Waiting for merge task {task_id} to complete")
                try:
                    # Wait with timeout
                    result = task_result.get(timeout=60)  # 1 minute timeout
                    
                    # If merge was successful, set the merged file path
                    output_path = os.path.join(self.task_dir, "Merged_pdf.pdf")
                    if result and os.path.exists(output_path):
                        self.state["merged_file"] = output_path
                        logger.info("Updated merged file path after waiting")
                    else:
                        logger.error("Task completed but merge failed after waiting")
                except Exception as e:
                    logger.error(f"Merge task {task_id} did not complete within timeout or failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error checking merge task {task_id} status: {str(e)}")
    
    def _handle_order_override(self, target_filename: str, new_order_str: str) -> tuple:
        """
        Handle order override for PDF merge workflow.
        
        Args:
            target_filename: Filename to reorder
            new_order_str: New order as string
            
        Returns:
            tuple: (success, message)
        """
        order_data = read_order_file(self.task_dir)
        
        if target_filename not in order_data:
            return False, "Cannot reorder the quoted message. Please reply directly to a PDF sent for this task."

        try:
            new_order = int(new_order_str)
            assert new_order > 0
        except (ValueError, AssertionError):
            return False, f"'{new_order_str}' invalid positive number."

        # Reorder logic
        other_items = sorted(
            [(fn, order) for fn, order in order_data.items() if fn != target_filename], 
            key=lambda i: i[1]
        )
        new_order_map = {target_filename: new_order}
        current_sequence_num = 1
        
        for filename, _ in other_items:
            while current_sequence_num == new_order:
                current_sequence_num += 1
            new_order_map[filename] = current_sequence_num
            current_sequence_num += 1

        if write_order_file(self.task_dir, new_order_map):
            return True, f"Order updated. The file is now number {new_order}."
        else:
            return False, "Failed to update order file."
    
    def _merge_pdfs_in_order(self, order_data: dict) -> tuple:
        """
        Merges PDFs based on order_data and saves as Merged_pdf.pdf.
        
        Args:
            order_data: Dictionary mapping filenames to their order
            
        Returns:
            tuple: (output_path, missing_files)
        """
        # Sort files by order
        sorted_files = sorted(order_data.items(), key=lambda item: item[1])
        input_files = []
        missing_files = []
        
        for filename, _ in sorted_files:
            file_path = os.path.join(self.task_dir, filename)
            if os.path.exists(file_path):
                input_files.append(file_path)
            else:
                missing_files.append(filename)
        
        if missing_files:
            logger.error(f"Missing files: {', '.join(missing_files)}")
            return None, missing_files
        
        if not input_files:
            logger.warning("No valid files to merge")
            return None, []
        
        # Define output path
        output_filename = "Merged_pdf.pdf"
        output_path = os.path.join(self.task_dir, output_filename)
        
        # Try to use Celery task for merging
        try:
            result = execute_task(merge_pdfs_task, input_files, output_path)
            
            # If result is a task instance, get the result
            if hasattr(result, 'get'):
                success = result.get(timeout=60)  # 1 minute timeout
            else:
                success = result
                
            if success and os.path.exists(output_path):
                logger.info("Merge completed successfully")
                return output_path, []
            else:
                logger.error("Failed to merge PDFs")
                return None, []
        except Exception as e:
            logger.error(f"Error in merge task: {str(e)}")
            
            # Fall back to direct merge if task fails
            logger.info("Falling back to direct PDF merge")
            return self._direct_merge_pdfs(input_files, output_path)
    
    def _direct_merge_pdfs(self, input_files: list, output_path: str) -> tuple:
        """
        Directly merge PDFs without using a Celery task.
        
        Args:
            input_files: List of PDF file paths
            output_path: Output file path
            
        Returns:
            tuple: (output_path, missing_files)
        """
        merger = PdfWriter()
        merged_something = False
        missing_files = []

        logger.info(f"Directly merging {len(input_files)} PDFs")

        for file_path in input_files:
            if os.path.exists(file_path):
                try:
                    merger.append(file_path)
                    merged_something = True
                except Exception as e:
                    logger.error(f"Error merging {os.path.basename(file_path)}: {e}")
                    missing_files.append(os.path.basename(file_path))
            else:
                missing_files.append(os.path.basename(file_path))

        if missing_files:
            logger.error(f"Missing files: {', '.join(missing_files)}")
            merger.close()
            return None, missing_files

        if not merged_something:
            logger.warning("No valid files to merge")
            merger.close()
            return None, []

        try:
            with open(output_path, "wb") as f_out:
                merger.write(f_out)
            merger.close()
            logger.info("Direct merge completed successfully")
            return output_path, []
        except Exception as e:
            logger.error(f"Error saving merged PDF: {str(e)}")
            merger.close()
            return None, []
