"""
Split PDF workflow for Document Scanner application.
"""

import os
import time
import re
import logging
from PyPDF2 import PdfReader, PdfWriter
from app.tasks import split_pdf_task
from app.celery_app import app as celery_app
from .base import BaseWorkflow
from utils.logging_utils import setup_logger

# Setup logger with our enhanced logging utilities
logger = setup_logger(__name__)

class SplitWorkflow(BaseWorkflow):
    """
    Workflow for splitting PDF documents.
    """
    
    # Class constants
    INSTRUCTION_MESSAGE = "Send me the PDF file you want to split."
    AWAITING_RANGES_MESSAGE = "Excellent! Now send me the page ranges you want to split out from this PDF.\n\n" \
                             "Example formats:\n" \
                             "- Single page: 5\n" \
                             "- Page range: 1-5\n" \
                             "- Multiple ranges: 1-3, 5, 7-9\n" \
                             "- From a page to the end: 5-end\n\n" \
                             "Reply with your page selection."
    
    # Time to wait between polling for task status (seconds)
    TASK_POLL_INTERVAL = 2
    # Maximum number of times to poll for task status before fallback to sync
    MAX_POLL_ATTEMPTS = 15  # 30 seconds with default 2 second interval
    
    def __init__(self, task_id, task_dir, sender_jid, whatsapp_client):
        """
        Initialize the workflow.
        
        Args:
            task_id (str): Unique ID for this task
            task_dir (str): Directory to store task files
            sender_jid (str): The user's JID
            whatsapp_client: WhatsApp client instance
        """
        super().__init__(task_id, task_dir, sender_jid, whatsapp_client)
        
        # Initialize workflow-specific state
        self.state.update({
            'pdf_file': None,
            'pdf_info': None,
            'page_ranges': None,
            'split_task_id': None,
            'last_poll_time': 0,
            'poll_attempts': 0,
            'continuation_requested': False,
            'original_filenames': {}  # To store original filenames
        })
        
    def handle_file_save(self, message_id, filename):
        """
        Handle saved PDF files.
        
        Args:
            message_id (str): ID of the message containing the file
            filename (str): Name of the saved file
            
        Returns:
            tuple: (result, message to user)
        """
        file_path = os.path.join(self.task_dir, filename)
        
        try:
            # Get PDF info (page count)
            with open(file_path, 'rb') as f:
                pdf_reader = PdfReader(f)
                page_count = len(pdf_reader.pages)
                
            # Store PDF info in state
            self.state['pdf_file'] = filename
            self.state['pdf_info'] = {
                'message_id': message_id,
                'filename': filename,
                'path': file_path,
                'page_count': page_count
            }
            
            # Send acknowledgment to user
            response = f"✅ PDF received ({page_count} pages). {self.AWAITING_RANGES_MESSAGE}"
            self.whatsapp_client.send_text(self.sender_jid, response)
            return filename, None
            
        except Exception as e:
            logger.error(f"Error processing PDF: {str(e)}")
            return None, "There was an error processing your PDF. Please try sending it again."
    
    def handle_command(self, message_text, quoted_stanza_id):
        """
        Handle text commands from the user.
        
        Args:
            message_text (str): The message text
            quoted_stanza_id (str): ID of the quoted message (if any)
            
        Returns:
            tuple: (is_done, response_message)
        """
        # If a task is currently processing, check if this is a continuation request
        if self.state.get('split_task_id') and message_text.lower().strip() in ['continue', 'yes', 'check', 'status']:
            self.state['continuation_requested'] = True
            return self._check_async_task_status()
        
        # If we're already processing and user didn't request to continue or cancel
        if self.state.get('split_task_id') and not message_text.lower().strip() in ['cancel', 'stop']:
            return False, "I'm still processing your previous split request. Type 'continue' to check status, or 'cancel' to stop."
            
        # If user wants to cancel the current task
        if self.state.get('split_task_id') and message_text.lower().strip() in ['cancel', 'stop']:
            # Try to revoke the Celery task
            try:
                celery_app.control.revoke(self.state['split_task_id'], terminate=True)
                logger.info(f"Task {self.state['split_task_id']} revoked at user request")
                self.state['split_task_id'] = None
                return True, "Split task cancelled. Send a new command to start over."
            except Exception as e:
                logger.error(f"Error cancelling task: {str(e)}")
                return True, "Error cancelling task. Let's start over anyway."
        
        # Make sure we have a PDF file
        if not self.state.get('pdf_file'):
            return False, "Please send me a PDF file first."
        
        # Process page range command
        pdf_info = self.state.get('pdf_info', {})
        page_count = pdf_info.get('page_count', 0)
        file_path = pdf_info.get('path', '')
        
        # Regex to validate page specifications
        # regex = r'(\d+)(?:-(\d+|end))?'
        page_ranges = []
        
        try:
            # Parse page ranges from the message
            parts = message_text.split(',')
            
            for part in parts:
                part = part.strip()
                
                # Check for single page
                if part.isdigit():
                    page_num = int(part)
                    if 1 <= page_num <= page_count:
                        page_ranges.append((page_num, page_num))
                    else:
                        return False, f"⚠️ Page {page_num} is out of range. The document has {page_count} pages."
                    continue
                    
                # Check for page range (e.g., "1-5" or "5-end")
                range_match = re.match(r'(\d+)-(\d+|end)', part)
                if range_match:
                    start, end = range_match.groups()
                    start = int(start)
                    
                    if end == 'end':
                        end = page_count
                    else:
                        end = int(end)
                    
                    if start > end:
                        return False, f"⚠️ Invalid range: {start}-{end}. Start page must be less than or equal to end page."
                        
                    if 1 <= start <= page_count and 1 <= end <= page_count:
                        page_ranges.append((start, end))
                    else:
                        return False, f"⚠️ Range {start}-{end} is out of bounds. The document has {page_count} pages."
                    continue
                    
                # If we get here, the format is invalid
                return False, f"⚠️ I couldn't understand the format: '{part}'. Please use formats like '5', '1-5', or '5-end'."
            
            # Make sure we have at least one range
            if not page_ranges:
                return False, "⚠️ Please specify at least one page or range."
                
            # Store the validated page ranges
            self.state['page_ranges'] = page_ranges
            
            # Start async task to split the PDF
            return self._start_split_task(file_path, page_ranges)
            
        except Exception as e:
            logger.error(f"Error parsing page ranges: {str(e)}")
            return False, "⚠️ Error processing your request. Please check your input and try again."
    
    def _start_split_task(self, file_path, page_ranges):
        """
        Start async task for PDF splitting.
        
        Args:
            file_path (str): Path to the PDF file
            page_ranges (list): List of (start, end) page ranges
            
        Returns:
            tuple: (is_done, response_message)
        """
        try:
            # Launch async task
            logger.info(f"Starting async PDF split task for {len(page_ranges)} ranges")
            
            task = split_pdf_task.delay(
                file_path=file_path,
                output_dir=self.task_dir,
                page_ranges=page_ranges
            )
            
            # Store the task ID
            self.state['split_task_id'] = task.id
            self.state['last_poll_time'] = time.time()
            self.state['poll_attempts'] = 0
            
            logger.info(f"Split task started with ID: {task.id}")
            
            # Check if task completed immediately (small PDFs)
            return self._check_async_task_status()
            
        except Exception as e:
            logger.error(f"Error starting split task: {str(e)}")
            
            # Fall back to synchronous execution
            logger.info("Falling back to synchronous split execution")
            return self._split_pdf_sync(file_path, page_ranges)
    
    def _check_async_task_status(self):
        """
        Check the status of the async split task.
        
        Returns:
            tuple: (is_done, response_message)
        """
        task_id = self.state.get('split_task_id')
        if not task_id:
            logger.error("No task ID found to check status")
            return False, "No task is currently running."
        
        # Enforce polling interval to avoid too many checks
        current_time = time.time()
        time_since_last_poll = current_time - self.state.get('last_poll_time', 0)
        
        # If we're checking too frequently and it's not a user-requested continuation
        if time_since_last_poll < self.TASK_POLL_INTERVAL and not self.state.get('continuation_requested'):
            time.sleep(self.TASK_POLL_INTERVAL - time_since_last_poll)
        
        # Update poll time
        self.state['last_poll_time'] = time.time()
        self.state['poll_attempts'] += 1
        
        try:
            # Check task status
            task = celery_app.AsyncResult(task_id)
            
            if task.ready():
                # Task completed
                if task.successful():
                    logger.info(f"Task {task_id} completed successfully")
                    
                    # Get the result (list of output filepaths)
                    result = task.get()
                    
                    # Store the result filepaths in state
                    self.state['output_files'] = result
                    
                    # Store original filenames for split outputs
                    pdf_info = self.state.get('pdf_info', {})
                    original_name = pdf_info.get('filename', '')
                    
                    # Create display names for split files
                    for i, filepath in enumerate(result):
                        output_filename = os.path.basename(filepath)
                        if original_name:
                            # Try to create a meaningful name
                            base_name, _ = os.path.splitext(original_name)
                            page_range = re.search(r'_pages_(\d+)-(\d+)\.pdf', output_filename)
                            if page_range:
                                start, end = page_range.groups()
                                display_name = f"{base_name}_pages_{start}-{end}.pdf"
                            else:
                                display_name = f"{base_name}_split_{i+1}.pdf"
                            
                            # Store the display name
                            self.state['original_filenames'][output_filename] = display_name
                    
                    # Clear the task ID since we're done
                    self.state['split_task_id'] = None
                    
                    # Complete the workflow
                    return True, f"✅ PDF split complete! Created {len(result)} file(s)."
                else:
                    # Task failed
                    logger.error(f"Task {task_id} failed: {task.result}")
                    
                    # Clear the task ID
                    self.state['split_task_id'] = None
                    
                    # Fall back to synchronous execution
                    logger.info("Falling back to synchronous split execution")
                    file_path = self.state.get('pdf_info', {}).get('path', '')
                    page_ranges = self.state.get('page_ranges', [])
                    
                    if file_path and page_ranges:
                        return self._split_pdf_sync(file_path, page_ranges)
                    else:
                        return False, "❌ There was an error processing your PDF. Please try again."
            else:
                # Task still running
                logger.debug(f"Task {task_id} still running (poll attempt {self.state['poll_attempts']})")
                
                # Calculate progress indicator based on poll attempts
                progress_percent = min(95, int((self.state['poll_attempts'] / self.MAX_POLL_ATTEMPTS) * 100))
                progress_bar = "▓" * (progress_percent // 10) + "░" * (10 - (progress_percent // 10))
                
                # If we've been polling too long, either inform the user or fall back to sync
                if self.state['poll_attempts'] >= self.MAX_POLL_ATTEMPTS:
                    if self.state.get('continuation_requested'):
                        # User has requested continuation, so just inform them it's still processing
                        self.state['continuation_requested'] = False
                        self.state['poll_attempts'] = 0  # Reset counter
                        
                        # Enhanced continuation message with options
                        return False, ("I'm still processing your PDF. This may take a while for larger files.\n\n"
                                     f"Progress: [{progress_bar}] ~{progress_percent}%\n\n"
                                     "Would you like to continue to iterate?\n\n"
                                     "Options:\n"
                                     "• Type 'yes' or 'continue' to check status again\n"
                                     "• Type 'cancel' to stop processing and start over")
                    else:
                        # We've waited too long automatically, fall back to sync
                        logger.warning(f"Task {task_id} taking too long, falling back to sync execution")
                        
                        # Try to revoke the task
                        celery_app.control.revoke(task_id, terminate=True)
                        
                        # Fall back to sync execution
                        file_path = self.state.get('pdf_info', {}).get('path', '')
                        page_ranges = self.state.get('page_ranges', [])
                        
                        self.state['split_task_id'] = None
                        
                        if file_path and page_ranges:
                            return self._split_pdf_sync(file_path, page_ranges)
                        else:
                            return False, "❌ There was an error processing your PDF. Please try again."
                else:
                    # Still within polling limits, wait for task to complete
                    if self.state.get('continuation_requested'):
                        # User explicitly asked for status
                        self.state['continuation_requested'] = False
                        
                        # Estimate remaining time
                        time_elapsed = self.state['poll_attempts'] * self.TASK_POLL_INTERVAL
                        est_total_time = (self.MAX_POLL_ATTEMPTS * self.TASK_POLL_INTERVAL)
                        est_time_remaining = max(0, est_total_time - time_elapsed)
                        
                        # Enhanced progress message
                        return False, (f"I'm still working on splitting your PDF.\n\n"
                                     f"Progress: [{progress_bar}] ~{progress_percent}%\n"
                                     f"Est. time remaining: ~{int(est_time_remaining)} seconds\n\n"
                                     "Options:\n"
                                     "• Type 'continue' to check status again\n"
                                     "• Type 'cancel' to stop processing and start over")
                    # Continue waiting
                    return False, None
        
        except Exception as e:
            logger.error(f"Error checking task status: {str(e)}")
            
            # Clear the task ID
            self.state['split_task_id'] = None
            
            # Fall back to synchronous execution
            logger.info("Falling back to synchronous split execution due to error")
            file_path = self.state.get('pdf_info', {}).get('path', '')
            page_ranges = self.state.get('page_ranges', [])
            
            if file_path and page_ranges:
                return self._split_pdf_sync(file_path, page_ranges)
            else:
                return False, "❌ There was an error processing your PDF. Please try again."
    
    def _split_pdf_sync(self, file_path, page_ranges):
        """
        Split PDF synchronously (fallback if async fails).
        
        Args:
            file_path (str): Path to the PDF file
            page_ranges (list): List of (start, end) page ranges
            
        Returns:
            tuple: (is_done, response_message)
        """
        try:
            logger.info("Executing PDF split synchronously")
            self.whatsapp_client.send_text(self.sender_jid, "Processing your PDF split request (synchronous mode)...")
            
            pdf_reader = PdfReader(file_path)
            output_files = []
            
            for i, (start_page, end_page) in enumerate(page_ranges):
                # Adjust for 0-based indexing
                start_idx = start_page - 1
                end_idx = end_page - 1
                
                pdf_writer = PdfWriter()
                
                # Add the specified pages
                for page_idx in range(start_idx, end_idx + 1):
                    pdf_writer.add_page(pdf_reader.pages[page_idx])
                
                # Write output file
                output_filename = f"split_{self.task_id}_pages_{start_page}-{end_page}.pdf"
                output_path = os.path.join(self.task_dir, output_filename)
                
                with open(output_path, 'wb') as output_file:
                    pdf_writer.write(output_file)
                
                output_files.append(output_path)
                
                # Store original filenames for split outputs
                pdf_info = self.state.get('pdf_info', {})
                original_name = pdf_info.get('filename', '')
                
                if original_name:
                    # Try to create a meaningful name
                    base_name, _ = os.path.splitext(original_name)
                    display_name = f"{base_name}_pages_{start_page}-{end_page}.pdf"
                    
                    # Store the display name
                    self.state['original_filenames'][os.path.basename(output_path)] = display_name
            
            # Store the output files in state
            self.state['output_files'] = output_files
            
            logger.info(f"Synchronous split completed, created {len(output_files)} files")
            return True, f"✅ PDF split complete! Created {len(output_files)} file(s)."
            
        except Exception as e:
            logger.error(f"Error in synchronous PDF split: {str(e)}")
            return False, "❌ There was an error splitting your PDF. Please try again."
    
    def finalize(self):
        """
        Finalize the workflow and return output files.
        
        Returns:
            list: List of output file paths
        """
        # Return the output files
        return self.state.get('output_files', [])
    
    @classmethod
    def get_instructions(cls):
        """
        Get instructions for this workflow.
        
        Returns:
            str: Instruction message
        """
        return cls.INSTRUCTION_MESSAGE
    
    @classmethod
    def from_dict(cls, data, whatsapp_client):
        """
        Create a workflow instance from a dictionary.
        
        Args:
            data (dict): Workflow state data
            whatsapp_client: WhatsApp client instance
            
        Returns:
            SplitWorkflow: Workflow instance
        """
        task_id = data.get('task_id')
        task_dir = data.get('task_dir')
        sender_jid = data.get('sender_jid')
        
        instance = cls(task_id, task_dir, sender_jid, whatsapp_client)
        instance.state = data.get('state', {})
        
        return instance
    
    def process_message(self, message_content):
        """
        Process a message from the user according to the current workflow state.
        
        Args:
            message_content (str): Message content from the user
        
        Returns:
            tuple: (should_continue, response_message)
        """
        current_step = self.state.get('step', 'init')
        logger.debug(f"Processing message in step: {current_step}")
        
        # Handle user requesting to check on task status
        if current_step == 'finalize' and message_content.strip().lower() in ['continue', 'yes', 'check', 'status', 'progress']:
            logger.info("User requested status check for split task")
            
            # Mark this as a user requested continuation
            self.state['continuation_requested'] = True
            
            # Check the task status
            return self._check_async_task_status()
        
        # Handle user requesting to cancel the task
        if current_step == 'finalize' and message_content.strip().lower() in ['cancel', 'stop', 'abort', 'no']:
            logger.info("User requested to cancel split task")
            
            task_id = self.state.get('split_task_id')
            if task_id:
                try:
                    # Try to revoke the task
                    celery_app.control.revoke(task_id, terminate=True)
                    self.state['split_task_id'] = None
                    return True, "❌ PDF splitting cancelled. You can start a new workflow."
                except Exception as e:
                    logger.error(f"Error cancelling task: {str(e)}")
                    return True, "❌ There was an error cancelling the task. Please try again."
            else:
                return True, "No task is currently running."
        
        # Handle initial step
        if current_step == 'init':
            # Check if we've got a PDF file
            if self._is_pdf_file(message_content):
                return self._handle_pdf_file(message_content)
            else:
                return False, "Please send me a PDF file to split."
        
        # Handle waiting for page ranges
        elif current_step == 'waiting_for_ranges':
            return self._handle_page_ranges(message_content)
        
        # Handle finalization step
        elif current_step == 'finalize':
            # If we're in finalize step but user sends something that's not a continuation check
            help_message = ("I'm currently processing your PDF splitting request. Options:\n"
                          "• Type 'continue' or 'status' to check progress\n"
                          "• Type 'cancel' to stop processing\n"
                          "• Or send a new PDF to start a new workflow")
            
            # Check if user sent a new PDF file
            if self._is_pdf_file(message_content):
                # Cancel any existing task
                task_id = self.state.get('split_task_id')
                if task_id:
                    try:
                        celery_app.control.revoke(task_id, terminate=True)
                    except Exception:
                        pass
                
                # Start fresh with new PDF
                return self._handle_pdf_file(message_content)
            
            return False, help_message
        
        # Unknown state
        logger.error(f"Unknown workflow state: {current_step}")
        return True, "Sorry, something went wrong. Please try again with a new PDF file."
