"""
PDF compression workflow handler for the Document Scanner application.
"""

import os
import logging
from typing import Dict, List, Tuple, Any, Optional

from workflows.base import BaseWorkflow
from utils.external_tools import compress_pdf
from utils.logging_utils import setup_logger
from utils.file_utils import check_file_exists_and_complete
from app.tasks import compress_pdf_task, execute_task

# Initialize logger with enhanced logging
logger = setup_logger(__name__)

class CompressPdfWorkflow(BaseWorkflow):
    """Handles PDF compression workflow."""
    
    # Compression levels with their Ghostscript settings and descriptions
    QUALITY_PRESETS = {
        "low": {
            "dpi": 150, 
            "jpeg_quality": 90,
            "pdfsettings": "/printer",
            "description": "Low compression (best quality, minor size reduction)"
        },
        "medium": {
            "dpi": 120, 
            "jpeg_quality": 80,
            "pdfsettings": "/ebook",
            "description": "Medium compression (good quality, moderate size reduction)"
        },
        "high": {
            "dpi": 96, 
            "jpeg_quality": 70,
            "pdfsettings": "/screen",
            "description": "High compression (adequate quality, significant size reduction)"
        },
        "max": {
            "dpi": 72, 
            "jpeg_quality": 60,
            "pdfsettings": "/ebook",  # Use ebook for max to maintain legibility while maximizing compression
            "description": "Maximum compression (lower quality, maximum size reduction)"
        }
    }
    
    # Mapping of numeric inputs to compression levels
    NUMERIC_TO_LEVEL = {
        "1": "low",
        "2": "medium", 
        "3": "high",
        "4": "max"
    }
    
    @classmethod
    def get_instructions(cls) -> str:
        """
        Get the user instructions for this workflow.
        
        Returns:
            str: User instructions
        """
        return ("Started PDF compression.\n"
                "Send me PDF files to compress their size.")

    @classmethod
    def get_initial_state(cls) -> Dict[str, Any]:
        """
        Get the initial state for this workflow.
        
        Returns:
            Dict[str, Any]: Initial workflow state
        """
        return {
            "compress_files": {},
            "quality_settings": {},
            "processed_files": {},  # Changed to dict to store message_id -> compressed_file mapping
            "original_sizes": {},
            "original_filenames": {},  # Added to match other workflows
            "task_ids": {},  # Track Celery task IDs
            "task_status": {}  # Track task status
        }
    
    def handle_command(self, message_text: str, quoted_stanza_id: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Handle commands for PDF compression.
        
        Args:
            message_text: Message text (command)
            quoted_stanza_id: ID of the quoted message (if any)
            
        Returns:
            Tuple[bool, Optional[str]]: (is_done, message)
        """
        message_text = message_text.lower().strip()
        
        # Check for task status queries
        if message_text == "status":
            return self._check_tasks_status()
        
        # Check if this is a reply to a PDF message
        if not quoted_stanza_id or quoted_stanza_id not in self.state.get("compress_files", {}):
            if message_text == "done":
                # If user types 'done', check if we have any files to process
                if self.state.get("compress_files"):
                    return True, "Compressing PDF files now..."
                else:
                    return False, "You haven't sent any PDF files yet. Please send PDFs to compress."
            
            # Handle standalone compression levels (not a reply to a specific PDF)
            if message_text in self.NUMERIC_TO_LEVEL or message_text in self.QUALITY_PRESETS:
                if not self.state.get("compress_files"):
                    return False, "Please send a PDF file first before selecting a compression level."
                
                # User has sent a compression level without replying to a specific PDF
                # Apply it to all pending files
                pending_files = list(self.state.get("compress_files", {}).items())
                
                if not pending_files:
                    return False, "No PDF files to compress. Please send PDFs first."
                
                # Determine the compression level
                compression_level = message_text
                if message_text in self.NUMERIC_TO_LEVEL:
                    compression_level = self.NUMERIC_TO_LEVEL[message_text]
                
                if compression_level not in self.QUALITY_PRESETS:
                    return False, "Invalid compression level. Choose from: 1-4 or low/medium/high/max"
                
                # Process all pending files
                processed_count = 0
                for msg_id, filename in pending_files:
                    # Skip already processed files
                    if msg_id in self.state.get("processed_files", {}):
                        continue
                        
                    success, _ = self._process_compression(msg_id, filename, compression_level)
                    if success:
                        processed_count += 1
                
                return True, f"Applied {compression_level} compression to {processed_count} PDF file(s). Processing now..."
            
            return False, "Please send a PDF file to compress, or reply to a PDF with compression level (1-4 or low/medium/high/max)."
        
        # This is a reply to a PDF, check for compression level
        pdf_filename = self.state["compress_files"][quoted_stanza_id]
        
        # Check for numeric input (1-4)
        if message_text in self.NUMERIC_TO_LEVEL:
            level = self.NUMERIC_TO_LEVEL[message_text]
            logger.info(f"Converting numeric input '{message_text}' to compression level: {level}")
        else:
            # Check for text input (low/medium/high/max)
            level = message_text
        
        # Process if valid compression level
        if level in self.QUALITY_PRESETS:
            # Store the requested compression level
            if "quality_settings" not in self.state:
                self.state["quality_settings"] = {}
            
            self.state["quality_settings"][quoted_stanza_id] = level
            
            # Process the PDF with the specified compression level
            return self._process_compression(quoted_stanza_id, pdf_filename, level)
        else:
            # Show compression options with predicted size reductions
            return self._show_compression_options(quoted_stanza_id, pdf_filename)
        
    def handle_file_save(self, message_id: str, saved_filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Handle saving a PDF file for compression.
        
        Args:
            message_id: Message ID of the received file
            saved_filename: Filename of the saved file
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (filename, message)
        """
        file_path = os.path.join(self.task_dir, saved_filename)
        
        # Check if file exists and is a PDF
        if not os.path.exists(file_path):
            return None, f"Failed to save the PDF file: {saved_filename}"
        
        # Store the file for future processing
        if "compress_files" not in self.state:
            self.state["compress_files"] = {}
            
        self.state["compress_files"][message_id] = saved_filename
        
        # Store original file size for later comparison
        file_size = os.path.getsize(file_path)
        if "original_sizes" not in self.state:
            self.state["original_sizes"] = {}
        self.state["original_sizes"][message_id] = file_size
        
        # Store the original filename using the common method
        self.store_original_filename(message_id, saved_filename)
        
        # Get original filename for display
        original_filename = None
        if 'original_filenames' in self.state and message_id in self.state['original_filenames']:
            original_filename = self.state['original_filenames'][message_id]
        else:
            original_filename = saved_filename
        
        # Show compression options with expected size reductions
        options_message = self._get_compression_options_message(file_path)
        
        # Build a more personalized message with the filename
        message = f"📄 Received: {original_filename}\n\n{options_message}"
        
        return saved_filename, message
    
    def finalize(self) -> List[str]:
        """
        Finalize the workflow and return output files.
        
        Returns:
            List[str]: List of output file paths
        """
        output_files = []
        
        # Wait for any pending tasks to complete
        self._wait_for_pending_tasks()
        
        # Process compressed files that are ready
        for message_id, output_path in self.state.get("processed_files", {}).items():
            if os.path.exists(output_path):
                # Track for output
                output_files.append(output_path)
                logger.info(f"Added compressed PDF to result list: {os.path.basename(output_path)}")
        
        # Process any uncompressed files with default compression
        for message_id, filename in self.state.get("compress_files", {}).items():
            # Skip if already processed
            if message_id in self.state.get("processed_files", {}):
                continue
                
            # Apply default (medium) compression
            input_path = os.path.join(self.task_dir, filename)
            output_filename = f"{os.path.splitext(filename)[0]}_compressed.pdf"
            output_path = os.path.join(self.task_dir, output_filename)
            
            if os.path.exists(input_path):
                logger.info(f"Applying default (medium) compression to {filename}")
                
                try:
                    # Use medium compression settings
                    settings = self.QUALITY_PRESETS["medium"]
                    
                    # Try to use Celery task for compression
                    try:
                        logger.info(f"Submitting default compression task for {filename}")
                        task_result = execute_task(
                            compress_pdf_task,
                            input_path, 
                            output_path, 
                            dpi=settings["dpi"], 
                            jpeg_quality=settings["jpeg_quality"],
                            pdfsettings=settings["pdfsettings"]
                        )
                        
                        # If executing synchronously, we have the result now
                        if hasattr(task_result, "get"):
                            # Asynchronous task - get result with timeout
                            result = task_result.get(timeout=300)  # 5 minute timeout
                        else:
                            # Synchronous execution - result is already available
                            result = task_result
                    except ImportError:
                        # Fall back to direct compression if Celery is not available
                        logger.info("Celery not available, falling back to direct compression")
                        result = compress_pdf(
                            input_path, 
                            output_path, 
                            dpi=settings["dpi"], 
                            jpeg_quality=settings["jpeg_quality"],
                            pdfsettings=settings["pdfsettings"]
                        )
                    
                    if result.get("success") and os.path.exists(output_path):
                        # Track the compressed file
                        if "processed_files" not in self.state:
                            self.state["processed_files"] = {}
                        self.state["processed_files"][message_id] = output_path
                        
                        # Add to output list
                        output_files.append(output_path)
                        logger.info(f"Added automatically compressed PDF to result list: {output_filename}")
                except Exception as e:
                    logger.error(f"Error applying default compression: {str(e)}")
        
        return output_files
    
    def _get_compression_options_message(self, pdf_path: str) -> str:
        """
        Generate a message showing compression options with expected size reductions.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            str: Message with compression options
        """
        original_size = os.path.getsize(pdf_path)
        
        # Format size based on magnitude
        size_str = self._format_file_size(original_size)
        
        message = f"PDF received - Original size: {size_str}\n\nChoose compression level (reply with option number):\n"
        
        # Add each compression option with expected size reduction
        for i, (level, settings) in enumerate(self.QUALITY_PRESETS.items(), 1):
            # Estimate reduction percentage based on compression level
            if level == "low":
                expected_reduction = 20
            elif level == "medium":
                expected_reduction = 40
            elif level == "high":
                expected_reduction = 60
            else:  # max
                expected_reduction = 75
                
            # Calculate expected size after compression
            expected_size = original_size * (1 - expected_reduction / 100)
            
            message += f"{i}. {level} - {settings['description']}\n"
            message += f"   Expected: {self._format_file_size(expected_size)} ({expected_reduction}% reduction)\n"
            
        message += "\nReply with 1, 2, 3, or 4 to select compression level"
        return message
    
    def _show_compression_options(self, message_id: str, pdf_filename: str) -> Tuple[bool, str]:
        """
        Show available compression options with expected size reductions.
        
        Args:
            message_id: Message ID of the PDF
            pdf_filename: Filename of the PDF
            
        Returns:
            Tuple[bool, str]: (is_done, message)
        """
        pdf_path = os.path.join(self.task_dir, pdf_filename)
        if not os.path.exists(pdf_path):
            return False, "PDF file not found. Please send the PDF again."
            
        return False, self._get_compression_options_message(pdf_path)
    
    def _process_compression(self, message_id: str, pdf_filename: str, quality_level: str) -> Tuple[bool, str]:
        """
        Process PDF compression with specified quality level.
        
        Args:
            message_id: Message ID of the PDF
            pdf_filename: Filename of the PDF
            quality_level: Compression quality level (low/medium/high/max)
            
        Returns:
            Tuple[bool, str]: (is_done, message)
        """
        # Validate compression level
        if quality_level not in self.QUALITY_PRESETS:
            return False, "Invalid compression level. Please choose between 1-4 or low/medium/high/max."
        
        settings = self.QUALITY_PRESETS[quality_level]
        
        # Input and output paths
        input_path = os.path.join(self.task_dir, pdf_filename)
        output_filename = f"{message_id}_compressed.pdf"  # Use message_id to ensure unique filenames
        output_path = os.path.join(self.task_dir, output_filename)
        
        try:
            # Get original file size for later comparison
            original_size = os.path.getsize(input_path)
            
            # Try to use Celery task for compression
            try:
                logger.info(f"Submitting compression task for {pdf_filename} with quality: {quality_level}")
                task_result = execute_task(
                    compress_pdf_task,
                    input_path, 
                    output_path, 
                    dpi=settings["dpi"], 
                    jpeg_quality=settings["jpeg_quality"],
                    pdfsettings=settings["pdfsettings"]
                )
                
                # Store task ID for status checks if it's an async task
                if hasattr(task_result, "id"):
                    if "task_ids" not in self.state:
                        self.state["task_ids"] = {}
                    if "task_status" not in self.state:
                        self.state["task_status"] = {}
                    
                    self.state["task_ids"][message_id] = task_result.id
                    self.state["task_status"][message_id] = "PENDING"
                    
                    # Send a message that compression is in progress
                    return False, (
                        f"Compression task started with {quality_level} quality.\n"
                        f"This may take a moment to complete.\n"
                        f"You can check status by typing 'status'."
                    )
                else:
                    # Task was executed synchronously, process the result now
                    result = task_result
                    return self._handle_compression_result(message_id, input_path, output_path, original_size, result)
                    
            except ImportError:
                # Fall back to direct compression if Celery is not available
                logger.info("Celery not available, falling back to direct compression")
                result = compress_pdf(
                    input_path, 
                    output_path, 
                    dpi=settings["dpi"], 
                    jpeg_quality=settings["jpeg_quality"],
                    pdfsettings=settings["pdfsettings"]
                )
                return self._handle_compression_result(message_id, input_path, output_path, original_size, result)
                
        except Exception as e:
            logger.error(f"Error compressing PDF: {str(e)}")
            return False, f"Error compressing PDF: {str(e)}"
    
    def _handle_compression_result(self, message_id: str, input_path: str, output_path: str, 
                                  original_size: int, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Handle the result of a compression task.
        
        Args:
            message_id: Message ID of the PDF
            input_path: Path to the input file
            output_path: Path to the output file
            original_size: Original file size in bytes
            result: Compression result dictionary
            
        Returns:
            Tuple[bool, str]: (is_done, message)
        """
        if result.get("success"):
            # If compression actually increases file size, use the original instead
            if os.path.exists(output_path):
                compressed_size = os.path.getsize(output_path)
                
                if compressed_size >= original_size:
                    logger.info("Compressed file is larger than original. Using original file.")
                    # Copy the original file to the compressed filename to maintain workflow
                    import shutil
                    shutil.copy2(input_path, output_path)
                    compressed_size = original_size
                    ratio = 0
                else:
                    # Calculate compression ratio
                    ratio = (1 - (compressed_size / original_size)) * 100
                
                # Store the compressed file in our tracking dictionary
                if "processed_files" not in self.state:
                    self.state["processed_files"] = {}
                    
                self.state["processed_files"][message_id] = output_path
                
                # Format sizes in appropriate units
                original_size_str = self._format_file_size(original_size)
                compressed_size_str = self._format_file_size(compressed_size)
                
                message = (
                    f"PDF compressed successfully with {self.state['quality_settings'].get(message_id, 'medium')} quality.\n"
                    f"Original: {original_size_str} → "
                    f"Compressed: {compressed_size_str} "
                )
                
                if ratio > 0:
                    message += f"({ratio:.1f}% reduction)"
                else:
                    message += "(No size reduction - using original file)"
                
                # Update task status
                if "task_status" in self.state and message_id in self.state["task_status"]:
                    self.state["task_status"][message_id] = "SUCCESS"
                
                return True, message
            else:
                return False, "Compression complete, but output file not found."
        else:
            error = result.get("error", "Unknown error")
            
            # Update task status
            if "task_status" in self.state and message_id in self.state["task_status"]:
                self.state["task_status"][message_id] = "FAILED"
                
            return False, f"Failed to compress PDF: {error}"
    
    def _check_tasks_status(self) -> Tuple[bool, str]:
        """
        Check status of all compression tasks.
        
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
            return False, "No compression tasks are in progress."
        
        pending_count = 0
        completed_count = 0
        failed_count = 0
        status_message = "Compression tasks status:\n"
        
        for message_id, task_id in self.state["task_ids"].items():
            try:
                # Get the task result object
                task_result = AsyncResult(task_id, app=app)
                
                # Update the task status
                status = task_result.status
                self.state["task_status"][message_id] = status
                
                # Get the original filename if available
                filename = None
                if "original_filenames" in self.state and message_id in self.state["original_filenames"]:
                    filename = self.state["original_filenames"][message_id]
                else:
                    filename = f"File {message_id}"
                    
                # Count by status
                if status in ['PENDING', 'STARTED', 'RETRY']:
                    pending_count += 1
                    status_message += f"- {filename}: {status}\n"
                elif status == 'SUCCESS':
                    completed_count += 1
                    
                    # If task is complete but result not handled yet, handle it now
                    if message_id not in self.state.get("processed_files", {}):
                        try:
                            # Get task result
                            result = task_result.get(timeout=10)
                            
                            # Find input and output paths
                            input_path = os.path.join(self.task_dir, self.state["compress_files"][message_id])
                            quality_level = self.state["quality_settings"].get(message_id, "medium")
                            output_filename = f"{message_id}_compressed.pdf"
                            output_path = os.path.join(self.task_dir, output_filename)
                            
                            # Process the result
                            original_size = self.state["original_sizes"].get(message_id, 0)
                            self._handle_compression_result(message_id, input_path, output_path, original_size, result)
                        except Exception as e:
                            logger.error(f"Error handling completed task result: {str(e)}")
                            
                    # Add to status message 
                    original_size = self.state["original_sizes"].get(message_id, 0)
                    output_path = self.state["processed_files"].get(message_id)
                    
                    if output_path and os.path.exists(output_path):
                        compressed_size = os.path.getsize(output_path)
                        ratio = (1 - (compressed_size / original_size)) * 100 if original_size > 0 else 0
                        status_message += f"- {filename}: COMPLETE ({ratio:.1f}% reduction)\n"
                    else:
                        status_message += f"- {filename}: COMPLETE\n"
                        
                elif status == 'FAILURE':
                    failed_count += 1
                    status_message += f"- {filename}: FAILED\n"
                    
            except Exception as e:
                logger.error(f"Error checking task status: {str(e)}")
                status_message += f"- Task {message_id}: ERROR checking status\n"
                
        # Summary
        status_message += f"\nSummary: {completed_count} complete, {pending_count} pending, {failed_count} failed"
        
        # If all tasks are done, return True to indicate we're ready to finalize
        all_done = pending_count == 0
        if all_done and (completed_count > 0 or failed_count > 0):
            status_message += "\n\nAll tasks complete. Type 'done' to finish and receive your files."
            
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
        
        logger.info("Checking for pending compression tasks before finalizing")
        
        for message_id, task_id in self.state["task_ids"].items():
            # Skip if already processed
            if message_id in self.state.get("processed_files", {}):
                continue
                
            try:
                # Get the task result
                task_result = AsyncResult(task_id, app=app)
                
                # If task is complete but not processed, handle it now
                if task_result.ready():
                    logger.info(f"Processing completed task {task_id} for message {message_id}")
                    
                    try:
                        # Get task result with a short timeout
                        result = task_result.get(timeout=30)
                        
                        # Find input and output paths
                        input_path = os.path.join(self.task_dir, self.state["compress_files"][message_id])
                        quality_level = self.state["quality_settings"].get(message_id, "medium")
                        output_filename = f"{message_id}_compressed.pdf"
                        output_path = os.path.join(self.task_dir, output_filename)
                        
                        # Process the result
                        original_size = self.state["original_sizes"].get(message_id, 0)
                        _, _ = self._handle_compression_result(message_id, input_path, output_path, original_size, result)
                    except Exception as e:
                        logger.error(f"Error processing completed task result during finalization: {str(e)}")
                else:
                    # For incomplete tasks, try to wait a short time
                    logger.info(f"Waiting for task {task_id} to complete")
                    try:
                        # Wait with timeout
                        result = task_result.get(timeout=60)  # 1 minute timeout
                        
                        # Process as above if we get a result
                        input_path = os.path.join(self.task_dir, self.state["compress_files"][message_id])
                        output_filename = f"{message_id}_compressed.pdf"
                        output_path = os.path.join(self.task_dir, output_filename)
                        original_size = self.state["original_sizes"].get(message_id, 0)
                        _, _ = self._handle_compression_result(message_id, input_path, output_path, original_size, result)
                    except Exception as e:
                        logger.error(f"Task {task_id} did not complete within timeout or failed: {str(e)}")
            except Exception as e:
                logger.error(f"Error checking task {task_id} status: {str(e)}")
    
    def _format_file_size(self, size_in_bytes: int) -> str:
        """
        Format file size in appropriate units (KB, MB, etc.)
        
        Args:
            size_in_bytes: Size in bytes
            
        Returns:
            str: Formatted size string
        """
        if size_in_bytes < 1024:
            return f"{size_in_bytes} bytes"
        elif size_in_bytes < 1024 * 1024:
            return f"{size_in_bytes / 1024:.1f} KB"
        else:
            return f"{size_in_bytes / (1024 * 1024):.2f} MB"