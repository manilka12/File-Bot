"""
PowerPoint to PDF conversion workflow handler for the Document Scanner application.
"""

import os
import logging
from workflows.base import BaseWorkflow
from utils.logging_utils import setup_logger
from utils.file_utils import check_file_exists_and_complete
from app.tasks import convert_document_task, execute_task
from app.exceptions import LibreOfficeError, ExternalToolError

# Initialize logger with enhanced logging
logger = setup_logger(__name__)

class PowerPointToPdfWorkflow(BaseWorkflow):
    """Handles the PowerPoint presentation to PDF conversion workflow."""
    
    @classmethod
    def get_instructions(cls):
        """
        Get the user instructions for this workflow.
        
        Returns:
            str: User instructions
        """
        return ("Started PowerPoint to PDF conversion.\n"
                "Send me PowerPoint presentations (.ppt or .pptx files) and I'll convert them to PDF.\n"
                "Type 'done' when you've sent all presentations to convert.")
    
    @classmethod
    def get_initial_state(cls):
        """
        Get the initial state for this workflow.
        
        Returns:
            dict: Initial workflow state
        """
        return {
            "presentation_versions": {},
            "original_filenames": {},
            "task_ids": {},  # Track Celery task IDs
            "task_status": {}  # Track task status
        }
    
    def handle_command(self, message_text, quoted_stanza_id):
        """
        Handle workflow commands.
        
        Args:
            message_text (str): Message text (command)
            quoted_stanza_id (str): ID of the quoted message (if any)
            
        Returns:
            tuple: (is_done, message) - Whether the workflow is done and a message to send
        """
        if message_text.lower() == "done":
            # Wait for any pending conversion tasks to complete before finalizing
            self._wait_for_pending_tasks()
            return True, "Processing your presentations..."
        
        # Check for status command
        if message_text.lower() == "status":
            return self._check_tasks_status()
        
        return False, "Send me PowerPoint presentations (.ppt or .pptx files) to convert to PDF, or type 'done' to finish."
    
    def handle_file_save(self, message_id, saved_filename):
        """
        Handles saving and processing a file for this workflow.
        
        Args:
            message_id (str): Message ID of the received file
            saved_filename (str): Filename for the saved file
            
        Returns:
            tuple: (saved_filename, message) - Filename and message to send
        """
        # Store the original filename using common method from BaseWorkflow
        self.store_original_filename(message_id, saved_filename)
        
        # Process the PowerPoint presentation
        file_path = os.path.join(self.task_dir, saved_filename)
        
        try:
            # Get file extension
            filename_base, filename_ext = os.path.splitext(saved_filename)
            
            # Generate output PDF filename using the original filename
            original_base = self.get_original_filename(message_id, filename_base)
            pdf_filename = f"{original_base}.pdf"
            pdf_path = os.path.join(self.task_dir, pdf_filename)
            
            # Check if it's a PowerPoint presentation
            if filename_ext.lower() not in ['.ppt', '.pptx', '.pptm']:
                logger.warning(f"Not a PowerPoint presentation: {saved_filename}")
                return saved_filename, f"File {saved_filename} is not a PowerPoint presentation. Please send a .ppt or .pptx file."
            
            logger.info(f"Converting PowerPoint presentation to PDF: {file_path}")
            
            # Convert PowerPoint presentation to PDF asynchronously using Celery task
            task_result = execute_task(convert_document_task, file_path, self.task_dir, doc_type='powerpoint')
            
            # Store task info for tracking
            if hasattr(task_result, 'id'):  # It's an async task
                # Store task ID for later reference
                if 'task_ids' not in self.state:
                    self.state['task_ids'] = {}
                if 'task_status' not in self.state:
                    self.state['task_status'] = {}
                
                self.state['task_ids'][message_id] = task_result.id
                self.state['task_status'][message_id] = 'PENDING'
                
                # Store temporary information in presentation_versions
                if 'presentation_versions' not in self.state:
                    self.state['presentation_versions'] = {}
                
                self.state['presentation_versions'][message_id] = {
                    'original': saved_filename,
                    'expected_pdf': pdf_filename,
                    'original_name': self.get_original_filename(message_id),
                    'conversion_status': 'pending'
                }
                
                return saved_filename, (
                    f"PowerPoint presentation received. Converting to PDF in the background.\n"
                    f"Type 'status' to check conversion progress or 'done' when finished."
                )
            else:
                # Task executed synchronously, process the result now
                output_pdf_path = task_result
                
                if output_pdf_path and os.path.exists(output_pdf_path):
                    # If the converted PDF has a different name, rename it to use the original name
                    if os.path.basename(output_pdf_path) != pdf_filename:
                        os.rename(output_pdf_path, pdf_path)
                        output_pdf_path = pdf_path
                    
                    logger.info(f"Successfully converted to PDF: {pdf_filename}")
                    
                    # Store the file references in workflow state
                    if 'presentation_versions' not in self.state:
                        self.state['presentation_versions'] = {}
                    
                    self.state['presentation_versions'][message_id] = {
                        'original': saved_filename,
                        'pdf': os.path.basename(output_pdf_path),
                        'original_name': self.get_original_filename(message_id),
                        'conversion_status': 'completed'
                    }
                    
                    return saved_filename, f"PowerPoint presentation converted to PDF successfully. The PDF will be available when you type 'done'."
                else:
                    logger.error(f"PDF conversion failed for {file_path}")
                    return saved_filename, f"Sorry, I couldn't convert {saved_filename} to PDF. Please try again with a different file."
            
        except Exception as e:
            logger.error(f"Error converting PowerPoint presentation to PDF: {str(e)}")
            return saved_filename, f"Error converting presentation: {str(e)}. Please try again with a different file."
    
    def finalize(self):
        """
        Finalize the workflow and return the output files.
        
        Returns:
            list: List of output file paths
        """
        output_files = []
        
        try:
            # Wait for any pending tasks to complete
            self._wait_for_pending_tasks()
            
            # Check if we have any presentations
            if 'presentation_versions' not in self.state or not self.state['presentation_versions']:
                logger.warning("No presentations received for conversion.")
                return []
            
            # Collect all PDF files
            for message_id, versions in self.state['presentation_versions'].items():
                if 'pdf' in versions:
                    pdf_path = os.path.join(self.task_dir, versions['pdf'])
                    if os.path.exists(pdf_path):
                        output_files.append(pdf_path)
                        logger.info(f"Added PDF to result list: {versions['pdf']}")
                    else:
                        logger.warning(f"PDF file not found: {versions['pdf']}")
            
            # Create a merged PDF if multiple presentations were converted
            if len(output_files) > 1:
                from pypdf import PdfReader, PdfWriter
                
                merged_pdf_path = os.path.join(self.task_dir, "Merged_Presentations.pdf")
                writer = PdfWriter()
                
                for pdf_path in output_files:
                    reader = PdfReader(pdf_path)
                    for page in reader.pages:
                        writer.add_page(page)
                
                with open(merged_pdf_path, "wb") as output_file:
                    writer.write(output_file)
                
                output_files.append(merged_pdf_path)
                logger.info(f"Created merged PDF: {merged_pdf_path}")
            
            return output_files
            
        except Exception as e:
            logger.error(f"Error finalizing PowerPoint to PDF task: {str(e)}")
            return output_files  # Return whatever we have even if there was an error
    
    def _check_tasks_status(self):
        """
        Check status of all conversion tasks.
        
        Returns:
            tuple: (is_done, message) - Whether the workflow is done and a message to send
        """
        try:
            # Import needed Celery components here to avoid circular imports
            from celery.result import AsyncResult
            from app.celery_app import app
        except ImportError:
            return False, "Task status checking not available (Celery not configured)"
        
        if not self.state.get("task_ids"):
            return False, "No conversion tasks are in progress."
        
        pending_count = 0
        completed_count = 0
        failed_count = 0
        status_message = "PowerPoint to PDF conversion status:\n"
        
        for message_id, task_id in self.state["task_ids"].items():
            try:
                # Get the task result object
                task_result = AsyncResult(task_id, app=app)
                
                # Update the task status
                status = task_result.status
                self.state["task_status"][message_id] = status
                
                # Get the original filename if available
                original_filename = self.get_original_filename(message_id, f"presentation_{message_id}")
                    
                # Count by status
                if status in ['PENDING', 'STARTED', 'RETRY']:
                    pending_count += 1
                    status_message += f"- {original_filename}: {status}\n"
                elif status == 'SUCCESS':
                    completed_count += 1
                    
                    # If task is complete but result not handled yet, handle it now
                    if message_id in self.state.get("presentation_versions", {}) and \
                       self.state["presentation_versions"][message_id].get("conversion_status") == "pending":
                        try:
                            # Get task result
                            output_pdf_path = task_result.get(timeout=10)
                            
                            if output_pdf_path and os.path.exists(output_pdf_path):
                                # Get expected PDF filename
                                expected_pdf = self.state["presentation_versions"][message_id].get("expected_pdf")
                                pdf_path = os.path.join(self.task_dir, expected_pdf)
                                
                                # If the converted PDF has a different name, rename it
                                if os.path.basename(output_pdf_path) != expected_pdf:
                                    os.rename(output_pdf_path, pdf_path)
                                    output_pdf_path = pdf_path
                                
                                # Update presentation_versions
                                self.state["presentation_versions"][message_id].update({
                                    'pdf': os.path.basename(output_pdf_path),
                                    'conversion_status': 'completed'
                                })
                                
                                logger.info(f"Updated status for completed task: {message_id}")
                            else:
                                self.state["presentation_versions"][message_id]['conversion_status'] = 'failed'
                                logger.error(f"Task completed but no PDF found for: {message_id}")
                        except Exception as e:
                            logger.error(f"Error handling completed task result: {str(e)}")
                            self.state["presentation_versions"][message_id]['conversion_status'] = 'failed'
                    
                    # Add to status message
                    status_message += f"- {original_filename}: COMPLETE\n"
                        
                elif status == 'FAILURE':
                    failed_count += 1
                    status_message += f"- {original_filename}: FAILED\n"
                    
                    # Update presentation_versions if needed
                    if message_id in self.state.get("presentation_versions", {}):
                        self.state["presentation_versions"][message_id]['conversion_status'] = 'failed'
                    
            except Exception as e:
                logger.error(f"Error checking task status for {message_id}: {str(e)}")
                status_message += f"- Task for presentation {message_id}: ERROR checking status\n"
                
        # Summary
        status_message += f"\nSummary: {completed_count} complete, {pending_count} pending, {failed_count} failed"
        
        # If all tasks are done, return True to indicate we're ready to finalize
        all_done = pending_count == 0
        if all_done and (completed_count > 0 or failed_count > 0):
            status_message += "\n\nAll conversions complete. Type 'done' to finish and receive your PDFs."
            
        return False, status_message
    
    def _wait_for_pending_tasks(self):
        """
        Wait for any pending tasks to complete before finalizing.
        """
        if not self.state.get("task_ids"):
            return
            
        try:
            # Import needed Celery components
            from celery.result import AsyncResult
            from app.celery_app import app
        except ImportError:
            logger.warning("Celery not available, skipping task waiting")
            return
        
        logger.info("Checking for pending conversion tasks before finalizing")
        
        for message_id, task_id in self.state["task_ids"].items():
            # Skip if already processed
            if message_id in self.state.get("presentation_versions", {}) and \
               self.state["presentation_versions"][message_id].get("conversion_status") == "completed":
                continue
                
            try:
                # Get the task result
                task_result = AsyncResult(task_id, app=app)
                
                # If task is complete but not processed, handle it now
                if task_result.ready():
                    logger.info(f"Processing completed task {task_id} for message {message_id}")
                    
                    try:
                        # Get task result with a short timeout
                        output_pdf_path = task_result.get(timeout=30)
                        
                        if output_pdf_path and os.path.exists(output_pdf_path):
                            # Get expected PDF filename
                            expected_pdf = self.state["presentation_versions"][message_id].get("expected_pdf")
                            pdf_path = os.path.join(self.task_dir, expected_pdf)
                            
                            # If the converted PDF has a different name, rename it
                            if os.path.basename(output_pdf_path) != expected_pdf:
                                os.rename(output_pdf_path, pdf_path)
                                output_pdf_path = pdf_path
                            
                            # Update presentation_versions
                            self.state["presentation_versions"][message_id].update({
                                'pdf': os.path.basename(output_pdf_path),
                                'conversion_status': 'completed'
                            })
                            
                            logger.info(f"Updated status during finalization for: {message_id}")
                        else:
                            self.state["presentation_versions"][message_id]['conversion_status'] = 'failed'
                            logger.error(f"Task completed but no PDF found for: {message_id}")
                    except Exception as e:
                        logger.error(f"Error processing completed task result during finalization: {str(e)}")
                        self.state["presentation_versions"][message_id]['conversion_status'] = 'failed'
                else:
                    # For incomplete tasks, try to wait a short time
                    logger.info(f"Waiting for task {task_id} to complete")
                    try:
                        # Wait with timeout
                        output_pdf_path = task_result.get(timeout=60)  # 1 minute timeout
                        
                        if output_pdf_path and os.path.exists(output_pdf_path):
                            # Process as above if we get a result
                            expected_pdf = self.state["presentation_versions"][message_id].get("expected_pdf")
                            pdf_path = os.path.join(self.task_dir, expected_pdf)
                            
                            if os.path.basename(output_pdf_path) != expected_pdf:
                                os.rename(output_pdf_path, pdf_path)
                                output_pdf_path = pdf_path
                            
                            self.state["presentation_versions"][message_id].update({
                                'pdf': os.path.basename(output_pdf_path),
                                'conversion_status': 'completed'
                            })
                        else:
                            self.state["presentation_versions"][message_id]['conversion_status'] = 'failed'
                    except Exception as e:
                        logger.error(f"Task {task_id} did not complete within timeout or failed: {str(e)}")
                        self.state["presentation_versions"][message_id]['conversion_status'] = 'failed'
            except Exception as e:
                logger.error(f"Error checking task {task_id} status: {str(e)}")