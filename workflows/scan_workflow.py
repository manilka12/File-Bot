"""
Document scanning workflow handler for the Document Scanner application.
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

from workflows.base import BaseWorkflow
from utils.logging_utils import setup_logger
from utils.file_utils import check_file_exists_and_complete
from app.tasks import scan_image_task, create_pdf_from_images_task, execute_task
from config.settings import SCAN_VERSIONS, MAX_WAIT_TIME

# Initialize logger
logger = setup_logger(__name__)

class ScanWorkflow(BaseWorkflow):
    """Handles the document scanning workflow."""
    
    @classmethod
    def get_instructions(cls) -> str:
        """
        Get the user instructions for this workflow.
        
        Returns:
            str: User instructions
        """
        return ("Started Document Scanner.\n"
                "Send me photos of documents to scan.\n"
                "Each photo will be processed to enhance readability.\n"
                "Type 'done' when you've sent all photos to process.")
    
    @classmethod
    def get_initial_state(cls) -> Dict[str, Any]:
        """
        Get the initial state for this workflow.
        
        Returns:
            Dict[str, Any]: Initial workflow state
        """
        return {
            "images": [],
            "image_versions": {},
            "original_filenames": {},
            "task_ids": {},  # Track Celery task IDs
            "task_status": {},  # Track task status
            "scan_tasks": {},  # Image ID to scan task ID mapping
            "pdf_task": None  # Task ID for the PDF creation task
        }
    
    def handle_command(self, message_text: str, quoted_stanza_id: Optional[str]) -> Tuple[bool, str]:
        """
        Handle workflow commands.
        
        Args:
            message_text: Message text (command)
            quoted_stanza_id: ID of the quoted message (if any)
            
        Returns:
            Tuple[bool, str]: (is_done, message)
        """
        command = message_text.lower().strip()
        
        if command == "done":
            # Check if we have any images
            if not self.state.get("images"):
                return False, "No images received yet. Please send at least one photo to scan."
                
            # Wait for any pending scan tasks to complete
            self._wait_for_pending_tasks()
            
            # Create PDF from processed images asynchronously
            self._create_pdfs_from_images()
            
            return True, "Processing your scanned images..."
            
        elif command == "status":
            return self._check_tasks_status()
        
        # For any other command, treat it as a request for instructions
        return False, ("Please send photos of documents to scan. "
                       "Each photo will be enhanced automatically. "
                       "Type 'done' when you've sent all photos to create PDFs.")
    
    def handle_file_save(self, message_id: str, saved_filename: str) -> Tuple[str, str]:
        """
        Handle saving an image file for scanning.
        
        Args:
            message_id: Message ID of the received file
            saved_filename: Filename of the saved file
            
        Returns:
            Tuple[str, str]: (filename, message)
        """
        # Store the original filename using common method from BaseWorkflow
        self.store_original_filename(message_id, saved_filename)
        
        # Add to images list
        if "images" not in self.state:
            self.state["images"] = []
            
        file_path = os.path.join(self.task_dir, saved_filename)
        
        # Verify the file exists
        if not os.path.exists(file_path):
            return saved_filename, "Failed to save the image file."
            
        # Add the filename to the list if not already present
        if saved_filename not in self.state["images"]:
            self.state["images"].append(saved_filename)
            
        # Start the image scanning task asynchronously
        self._start_scan_task(message_id, saved_filename)
            
        return saved_filename, "Photo received. Processing scan... You'll see results when complete or when you type 'done'."
    
    def _start_scan_task(self, message_id: str, saved_filename: str) -> None:
        """
        Start an asynchronous task to scan an image.
        
        Args:
            message_id: Message ID of the image
            saved_filename: Filename of the image
        """
        file_path = os.path.join(self.task_dir, saved_filename)
        
        # Execute the scan task
        task_result = execute_task(scan_image_task, file_path, self.task_dir)
        
        # Store task info for tracking
        if hasattr(task_result, 'id'):  # It's an async task
            if 'task_ids' not in self.state:
                self.state['task_ids'] = {}
            if 'task_status' not in self.state:
                self.state['task_status'] = {}
            if 'scan_tasks' not in self.state:
                self.state['scan_tasks'] = {}
                
            self.state['task_ids'][task_result.id] = message_id  # Reverse mapping for task status check
            self.state['task_status'][task_result.id] = 'PENDING'
            self.state['scan_tasks'][message_id] = task_result.id  # Map image ID to task ID
            
            logger.info(f"Started async scan task for {saved_filename} with task ID: {task_result.id}")
        else:
            # Task executed synchronously, store the result now
            result = task_result
            
            if not self.state.get("image_versions"):
                self.state["image_versions"] = {}
                
            self.state["image_versions"][message_id] = result
            logger.info(f"Completed synchronous scan for {saved_filename}")
    
    def _create_pdfs_from_images(self) -> None:
        """
        Start an asynchronous task to create PDFs from the processed images.
        """
        # Check if we have any processed images
        if not self.state.get("images"):
            logger.warning("No images to create PDFs from")
            return
            
        # Get all image paths
        image_paths = [os.path.join(self.task_dir, filename) for filename in self.state.get("images", [])]
        
        # Execute the PDF creation task
        task_result = execute_task(create_pdf_from_images_task, image_paths, self.task_dir, SCAN_VERSIONS)
        
        # Store task info for tracking
        if hasattr(task_result, 'id'):  # It's an async task
            if 'task_ids' not in self.state:
                self.state['task_ids'] = {}
            if 'task_status' not in self.state:
                self.state['task_status'] = {}
                
            self.state['task_ids'][task_result.id] = 'pdf_creation'
            self.state['task_status'][task_result.id] = 'PENDING'
            self.state['pdf_task'] = task_result.id
            
            logger.info(f"Started async PDF creation task with task ID: {task_result.id}")
        else:
            # Task executed synchronously, store the result now
            result = task_result
            
            if result:
                self.state["pdf_paths"] = result
                logger.info(f"Completed synchronous PDF creation with {len(result)} PDFs")
            else:
                logger.error("Synchronous PDF creation failed")
    
    def finalize(self) -> List[str]:
        """
        Finalize the workflow and return the output files.
        
        Returns:
            List[str]: List of output file paths
        """
        result_files = []
        
        try:
            # Wait for any pending tasks to complete
            self._wait_for_pending_tasks()
            
            # If no PDFs created yet (e.g., tasks were synchronous), create them now
            if not self.state.get("pdf_paths") and self.state.get("images"):
                # Try to create PDFs directly
                try:
                    from app.tasks import create_pdf_from_images_task
                    
                    # Get all image paths
                    image_paths = [os.path.join(self.task_dir, filename) for filename in self.state.get("images", [])]
                    
                    # Create PDFs
                    pdf_paths = create_pdf_from_images_task(None, image_paths, self.task_dir, SCAN_VERSIONS)
                    
                    if pdf_paths:
                        self.state["pdf_paths"] = pdf_paths
                    else:
                        logger.error("Failed to create PDFs in finalize")
                except Exception as e:
                    logger.error(f"Error creating PDFs in finalize: {str(e)}")
            
            # Return the PDF files
            pdf_paths = self.state.get("pdf_paths", [])
            for pdf_path in pdf_paths:
                if os.path.exists(pdf_path):
                    result_files.append(pdf_path)
                    logger.info(f"Added PDF to result list: {os.path.basename(pdf_path)}")
                else:
                    logger.warning(f"PDF file not found: {pdf_path}")
            
            # If no PDFs available, return all the enhanced images as fallback
            if not result_files:
                logger.warning("No PDFs available. Returning enhanced images instead.")
                
                for message_id, versions in self.state.get("image_versions", {}).items():
                    for version_type, version_filename in versions.items():
                        if version_type in ['bw', 'magic_color', 'enhanced']:
                            image_path = os.path.join(self.task_dir, version_filename)
                            if os.path.exists(image_path):
                                result_files.append(image_path)
                                logger.info(f"Added enhanced image to result list: {version_filename}")
                
                # If we still have no results, return the original images as last resort
                if not result_files:
                    logger.warning("No enhanced images available. Returning original images.")
                    for filename in self.state.get("images", []):
                        image_path = os.path.join(self.task_dir, filename)
                        if os.path.exists(image_path):
                            result_files.append(image_path)
                            logger.info(f"Added original image to result list: {filename}")
            
            logger.info(f"Returning {len(result_files)} result files")
            return result_files
            
        except Exception as e:
            logger.error(f"Error finalizing scan workflow: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return result_files  # Return whatever we have
    
    def _check_tasks_status(self) -> Tuple[bool, str]:
        """
        Check status of all scanning tasks.
        
        Returns:
            Tuple[bool, str]: (is_done, message)
        """
        try:
            # Import needed Celery components here to avoid circular imports
            from celery.result import AsyncResult
            from app.celery_app import app
        except ImportError:
            return False, "Task status checking not available (Celery not configured)"
        
        if not self.state.get("task_ids"):
            return False, "No scanning tasks are in progress."
        
        pending_count = 0
        completed_count = 0
        failed_count = 0
        status_message = "Document scanning status:\n"
        
        # First check scan tasks
        for message_id, task_id in self.state.get("scan_tasks", {}).items():
            try:
                # Get the task result object
                task_result = AsyncResult(task_id, app=app)
                
                # Update the task status
                status = task_result.status
                self.state["task_status"][task_id] = status
                
                # Get the original filename if available
                original_name = self.get_original_filename(message_id, f"image_{message_id}")
                    
                # Count by status
                if status in ['PENDING', 'STARTED', 'RETRY']:
                    pending_count += 1
                    status_message += f"- {original_name}: {status}\n"
                elif status == 'SUCCESS':
                    completed_count += 1
                    
                    # If task is complete but result not handled yet, handle it now
                    if message_id not in self.state.get("image_versions", {}):
                        try:
                            # Get task result
                            result = task_result.get(timeout=10)
                            
                            if result:
                                # Store the image versions
                                if not self.state.get("image_versions"):
                                    self.state["image_versions"] = {}
                                self.state["image_versions"][message_id] = result
                                
                                logger.info(f"Updated status for completed scan task: {message_id}")
                            else:
                                logger.error(f"Task completed but no output produced for: {message_id}")
                        except Exception as e:
                            logger.error(f"Error handling completed scan task result: {str(e)}")
                    
                    status_message += f"- {original_name}: COMPLETE\n"
                        
                elif status == 'FAILURE':
                    failed_count += 1
                    status_message += f"- {original_name}: FAILED\n"
                    
            except Exception as e:
                logger.error(f"Error checking task status for {message_id}: {str(e)}")
                status_message += f"- Task for image {message_id}: ERROR checking status\n"
                
        # Then check PDF creation task if exists
        if self.state.get("pdf_task"):
            pdf_task_id = self.state["pdf_task"]
            try:
                task_result = AsyncResult(pdf_task_id, app=app)
                status = task_result.status
                self.state["task_status"][pdf_task_id] = status
                
                if status in ['PENDING', 'STARTED', 'RETRY']:
                    pending_count += 1
                    status_message += f"- PDF creation: {status}\n"
                elif status == 'SUCCESS':
                    completed_count += 1
                    
                    # If task is complete but result not handled yet, handle it now
                    if not self.state.get("pdf_paths"):
                        try:
                            # Get task result
                            result = task_result.get(timeout=10)
                            
                            if result:
                                self.state["pdf_paths"] = result
                                status_message += f"- PDF creation: COMPLETE - Created {len(result)} PDFs\n"
                                logger.info("Updated status for completed PDF creation task")
                            else:
                                status_message += "- PDF creation: FAILED - No PDFs produced\n"
                                logger.error("PDF task completed but no PDFs produced")
                        except Exception as e:
                            logger.error(f"Error handling completed PDF task result: {str(e)}")
                            status_message += f"- PDF creation: ERROR - {str(e)}\n"
                    else:
                        # Already processed
                        pdf_count = len(self.state.get("pdf_paths", []))
                        status_message += f"- PDF creation: COMPLETE - Created {pdf_count} PDFs\n"
                        
                elif status == 'FAILURE':
                    failed_count += 1
                    status_message += "- PDF creation: FAILED\n"
            except Exception as e:
                logger.error(f"Error checking PDF creation task status: {str(e)}")
                status_message += "- PDF creation task: ERROR checking status\n"
                
        # Summary
        status_message += f"\nSummary: {completed_count} complete, {pending_count} pending, {failed_count} failed"
        
        # If all tasks are done, suggest finishing
        if pending_count == 0 and (completed_count > 0 or failed_count > 0):
            status_message += "\n\nAll scanning tasks complete. Type 'done' to finish and receive your files."
            
        return False, status_message
    
    def _wait_for_pending_tasks(self) -> None:
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
        
        # Set maximum wait time
        max_wait = MAX_WAIT_TIME  # In seconds
        start_time = time.time()
        
        logger.info("Checking for pending scan tasks before finalizing")
        
        # First wait for all scan tasks to complete
        for message_id, task_id in list(self.state.get("scan_tasks", {}).items()):
            # Skip if already processed
            if message_id in self.state.get("image_versions", {}):
                continue
                
            # Check if we've exceeded max wait time
            if time.time() - start_time > max_wait:
                logger.warning(f"Exceeded maximum wait time of {max_wait} seconds")
                break
                
            try:
                # Get the task result
                task_result = AsyncResult(task_id, app=app)
                
                # If task is ready, get the result
                if task_result.ready():
                    logger.info(f"Processing completed scan task {task_id} for message {message_id}")
                    
                    try:
                        # Get task result with a short timeout
                        result = task_result.get(timeout=30)
                        
                        if result:
                            # Store the image versions
                            if not self.state.get("image_versions"):
                                self.state["image_versions"] = {}
                            self.state["image_versions"][message_id] = result
                            
                            logger.info(f"Updated image versions during finalization for: {message_id}")
                        else:
                            logger.error(f"Task completed but no output produced for: {message_id}")
                    except Exception as e:
                        logger.error(f"Error processing completed scan task result during finalization: {str(e)}")
                else:
                    # For incomplete tasks, try to wait a short time
                    logger.info(f"Waiting for scan task {task_id} to complete")
                    try:
                        # Wait with timeout (divide remaining time by number of tasks)
                        remaining_time = max_wait - (time.time() - start_time)
                        timeout = min(60, max(5, remaining_time / len(self.state.get("scan_tasks", {}))))
                        result = task_result.get(timeout=timeout)
                        
                        if result:
                            # Store the image versions
                            if not self.state.get("image_versions"):
                                self.state["image_versions"] = {}
                            self.state["image_versions"][message_id] = result
                            
                            logger.info(f"Updated image versions after waiting for: {message_id}")
                        else:
                            logger.error(f"Task completed but no output produced after waiting for: {message_id}")
                    except Exception as e:
                        logger.error(f"Task {task_id} did not complete within timeout or failed: {str(e)}")
            except Exception as e:
                logger.error(f"Error checking scan task {task_id} status: {str(e)}")
        
        # Then wait for the PDF creation task if it exists
        if self.state.get("pdf_task") and not self.state.get("pdf_paths"):
            # Check if we've exceeded max wait time
            if time.time() - start_time > max_wait:
                logger.warning(f"Exceeded maximum wait time of {max_wait} seconds, skipping PDF task wait")
                return
                
            pdf_task_id = self.state["pdf_task"]
            try:
                task_result = AsyncResult(pdf_task_id, app=app)
                
                if task_result.ready():
                    logger.info(f"Processing completed PDF creation task {pdf_task_id}")
                    
                    try:
                        # Get task result with a short timeout
                        result = task_result.get(timeout=30)
                        
                        if result:
                            self.state["pdf_paths"] = result
                            logger.info("Updated PDF paths during finalization")
                        else:
                            logger.error("PDF task completed but no PDFs produced")
                    except Exception as e:
                        logger.error(f"Error processing completed PDF task result during finalization: {str(e)}")
                else:
                    # Try to wait a short time for the PDF creation task
                    logger.info(f"Waiting for PDF creation task {pdf_task_id} to complete")
                    try:
                        # Wait with timeout (use remaining time)
                        remaining_time = max_wait - (time.time() - start_time)
                        timeout = min(60, max(5, remaining_time))
                        result = task_result.get(timeout=timeout)
                        
                        if result:
                            self.state["pdf_paths"] = result
                            logger.info("Updated PDF paths after waiting")
                        else:
                            logger.error("PDF task completed but no PDFs produced after waiting")
                    except Exception as e:
                        logger.error(f"PDF task {pdf_task_id} did not complete within timeout or failed: {str(e)}")
            except Exception as e:
                logger.error(f"Error checking PDF task {pdf_task_id} status: {str(e)}")
