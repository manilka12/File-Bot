"""
Workflow manager for the Document Scanner application.
"""

import os
import uuid
import base64
import logging
from utils.file_utils import cleanup_task_universal, read_order_file
from utils.logging_utils import setup_logger, set_context, with_context
from utils.persistence import get_state_manager
from app.exceptions import StateManagementError

from workflows.base import BaseWorkflow
from workflows.merge_workflow import MergeWorkflow
from workflows.split_workflow import SplitWorkflow
from workflows.scan_workflow import ScanWorkflow
from workflows.word_to_pdf_workflow import WordToPdfWorkflow
from workflows.powerpoint_to_pdf_workflow import PowerPointToPdfWorkflow
from workflows.excel_to_pdf_workflow import ExcelToPdfWorkflow
from workflows.compress_pdf_workflow import CompressPdfWorkflow
from workflows.markdown_to_pdf_workflow import MarkdownToPdfWorkflow

from config.settings import DOWNLOAD_BASE_DIR

# Setup logger with our enhanced logging utilities
logger = setup_logger(__name__)

class WorkflowManager:
    """Manages workflows for document processing tasks."""
    
    # Map workflow types to their respective classes
    WORKFLOW_CLASSES = {
        "merge": MergeWorkflow,
        "split": SplitWorkflow,
        "scan": ScanWorkflow,
        "word_to_pdf": WordToPdfWorkflow,
        "powerpoint_to_pdf": PowerPointToPdfWorkflow,
        "excel_to_pdf": ExcelToPdfWorkflow,
        "compress": CompressPdfWorkflow,
        "markdown_to_pdf": MarkdownToPdfWorkflow
    }
    
    def __init__(self, whatsapp_client):
        """
        Initialize the workflow manager.
        
        Args:
            whatsapp_client: Instance of WhatsAppClient
        """
        self.whatsapp_client = whatsapp_client
        
        try:
            # Initialize the state manager for persistent workflow state
            self.state_manager = get_state_manager()
            
            # Check what type of state manager we're using
            from utils.persistence import RedisStateManager
            if isinstance(self.state_manager, RedisStateManager):
                logger.info("WorkflowManager initialized with Redis state persistence")
            else:
                logger.info("WorkflowManager initialized with in-memory state persistence")
                
        except StateManagementError as e:
            logger.error(f"Failed to initialize state persistence: {str(e)}")
            logger.warning("Falling back to in-memory state management")
            self.state_manager = None
            self.active_workflows = {}  # Fallback to in-memory storage
            logger.info("WorkflowManager initialized with in-memory state persistence")
    
    def _get_workflow_instance(self, sender_jid):
        """
        Get the workflow instance for a user.
        
        Args:
            sender_jid (str): The user's JID
            
        Returns:
            BaseWorkflow: Workflow instance or None if not found
        """
        # Get workflow data from persistence
        workflow_data = self._get_workflow_state(sender_jid)
        if not workflow_data:
            return None
            
        # Extract workflow type
        workflow_type = workflow_data.get("workflow_type")
        if not workflow_type:
            logger.error(f"Missing workflow type in persisted data for {sender_jid}")
            return None
            
        # Handle variations in workflow type formats
        if workflow_type not in self.WORKFLOW_CLASSES:
            # Try alternative formats
            normalized_type = workflow_type.replace("_pdf", "").replace("pdf_", "")
            
            # Handle specific cases
            if workflow_type == "word_to_pdf":
                normalized_type = "word_to_pdf"
            elif workflow_type == "powerpoint_to_pdf" or workflow_type == "power_point_to_pdf":
                normalized_type = "powerpoint_to_pdf"
            elif workflow_type == "excel_to_pdf":
                normalized_type = "excel_to_pdf" 
            elif workflow_type == "markdown_to_pdf":
                normalized_type = "markdown_to_pdf"
            
            if normalized_type in self.WORKFLOW_CLASSES:
                logger.info(f"Normalized workflow type from '{workflow_type}' to '{normalized_type}'")
                workflow_type = normalized_type
                # Update the stored data for future lookups
                workflow_data["workflow_type"] = normalized_type
            else:
                logger.error(f"Invalid workflow type in persisted data: {workflow_type}")
                return None
            
        # Get the workflow class
        workflow_class = self.WORKFLOW_CLASSES[workflow_type]
        
        # Create an instance from persisted data
        try:
            workflow_data["sender_jid"] = sender_jid
            workflow_instance = workflow_class.from_dict(workflow_data, self.whatsapp_client)
            return workflow_instance
        except Exception as e:
            logger.error(f"Error creating workflow instance: {str(e)}")
            return None
    
    def _save_workflow_instance(self, sender_jid, workflow_instance):
        """
        Save a workflow instance.
        
        Args:
            sender_jid (str): The user's JID
            workflow_instance (BaseWorkflow): The workflow instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert instance to dict for persistence
            workflow_data = workflow_instance.to_dict()
            # Add sender_jid to the data
            workflow_data["sender_jid"] = sender_jid
            # Save to persistence
            return self._save_workflow_state(sender_jid, workflow_data)
        except Exception as e:
            logger.error(f"Error saving workflow instance: {str(e)}")
            return False
    
    def _get_workflow_state(self, sender_jid):
        """
        Get the workflow state for a user.
        
        Args:
            sender_jid (str): The user's JID
            
        Returns:
            dict: Workflow state or None if not found
        """
        if self.state_manager:
            try:
                return self.state_manager.load_workflow_state(sender_jid)
            except StateManagementError as e:
                logger.error(f"Error loading workflow state: {str(e)}")
                return self.active_workflows.get(sender_jid) if hasattr(self, 'active_workflows') else None
        else:
            return self.active_workflows.get(sender_jid)
    
    def _save_workflow_state(self, sender_jid, state):
        """
        Save the workflow state for a user.
        
        Args:
            sender_jid (str): The user's JID
            state (dict): Workflow state to save
            
        Returns:
            bool: True if successful, False otherwise
        """
        if self.state_manager:
            try:
                return self.state_manager.save_workflow_state(sender_jid, state)
            except StateManagementError as e:
                logger.error(f"Error saving workflow state: {str(e)}")
                if hasattr(self, 'active_workflows'):
                    self.active_workflows[sender_jid] = state
                return False
        else:
            self.active_workflows[sender_jid] = state
            return True
    
    def _delete_workflow_state(self, sender_jid):
        """
        Delete the workflow state for a user.
        
        Args:
            sender_jid (str): The user's JID
            
        Returns:
            bool: True if successful, False otherwise
        """
        if self.state_manager:
            try:
                return self.state_manager.delete_workflow_state(sender_jid)
            except StateManagementError as e:
                logger.error(f"Error deleting workflow state: {str(e)}")
                if hasattr(self, 'active_workflows') and sender_jid in self.active_workflows:
                    del self.active_workflows[sender_jid]
                return False
        else:
            if sender_jid in self.active_workflows:
                del self.active_workflows[sender_jid]
            return True
    
    @with_context(task_id="workflow_start", sender_jid="system")
    def start_workflow(self, sender_jid, workflow_type):
        """
        Start a new workflow for a user.
        
        Args:
            sender_jid (str): The user's JID
            workflow_type (str): Type of workflow ('merge', 'split', 'scan', etc.)
            
        Returns:
            tuple: (success, message)
        """
        # Update logging context for this specific workflow start
        set_context(sender_jid=sender_jid, task_id="workflow_start")
        logger.info(f"Starting {workflow_type} workflow")
        
        # Check if workflow type is valid
        if workflow_type not in self.WORKFLOW_CLASSES:
            logger.error(f"Invalid workflow type requested: {workflow_type}")
            return False, "Invalid workflow type."
        
        workflow_class = self.WORKFLOW_CLASSES[workflow_type]
        
        # Create task directory
        task_id = str(uuid.uuid4())
        safe_sender_jid = "".join(c if c.isalnum() else "_" for c in sender_jid)
        task_dir = os.path.join(DOWNLOAD_BASE_DIR, safe_sender_jid, task_id)
        
        # Update logging context with the generated task_id
        set_context(task_id=task_id)
        
        try:
            os.makedirs(task_dir, exist_ok=True)
            
            # Create new workflow instance
            workflow_instance = workflow_class(
                task_id=task_id,
                task_dir=task_dir,
                sender_jid=sender_jid,
                whatsapp_client=self.whatsapp_client
            )
            
            # Save the workflow instance
            if not self._save_workflow_instance(sender_jid, workflow_instance):
                raise StateManagementError("Failed to save workflow state")
            
            logger.info(f"Created task directory: {task_dir}")
            
            # Get instructions from workflow class
            instruction_message = workflow_class.get_instructions()
            
            # Send instructions to user
            self.whatsapp_client.send_text(sender_jid, instruction_message)
            logger.info("Instructions sent to user")
            return True, task_dir
            
        except Exception as e:
            logger.error(f"Failed to start workflow: {str(e)}")
            return False, f"Sorry, failed to start the {workflow_type} process."
    
    @with_context()
    def handle_pdf_save(self, sender_jid, message_data):
        """
        Handle saving PDF files for any workflow.
        
        Args:
            sender_jid (str): The user's JID
            message_data (dict): The message data
            
        Returns:
            str: Saved filename if successful, None otherwise
        """
        # Get workflow instance for this user
        workflow_instance = self._get_workflow_instance(sender_jid)
        if not workflow_instance:
            logger.warning(f"Received PDF from user without active workflow: {sender_jid}")
            return None

        # Set context for consistent logging
        set_context(sender_jid=sender_jid, task_id=workflow_instance.task_id)
        
        # Extract message info
        message_id = message_data.get('key', {}).get('id')
        message_holder = message_data.get('message', {})
        base64_string = message_holder.get('base64')
        doc_message = message_holder.get('documentMessage', {})
        mimetype = doc_message.get('mimetype')
        
        # Extract original filename from document message
        original_filename = doc_message.get('fileName')
        
        if not all([message_id, base64_string, mimetype == 'application/pdf']):
            logger.warning("Invalid PDF message format")
            return None

        saved_filename = f"{message_id}.pdf"
        file_path = os.path.join(workflow_instance.task_dir, saved_filename)
        
        try:
            # Save PDF
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(base64_string))

            logger.info(f"Saved PDF: {saved_filename}, Original name: {original_filename}")
            
            # Store original filename in the workflow state for ALL workflows (not just compress)
            if original_filename:
                workflow_instance.state["original_filename"] = original_filename
                logger.info(f"Stored original filename in workflow state: {original_filename}")
            
            # Still maintain backward compatibility with compress workflow
            if original_filename and workflow_instance.__class__.__name__ == "CompressPdfWorkflow":
                if "original_filenames" not in workflow_instance.state:
                    workflow_instance.state["original_filenames"] = {}
                workflow_instance.state["original_filenames"][message_id] = original_filename
                logger.info(f"Stored original filename for {message_id}: {original_filename}")
            
            # Store document message info in workflow state
            workflow_instance.state["document_message"] = doc_message
            
            # Let the workflow instance handle the file
            result, message = workflow_instance.handle_file_save(message_id, saved_filename)
            
            # Save updated workflow state
            self._save_workflow_instance(sender_jid, workflow_instance)
            
            # Send any response message to the user (if not already sent by the workflow)
            if message and self.whatsapp_client:
                self.whatsapp_client.send_text(sender_jid, message)
                
            return result

        except Exception as e:
            logger.error(f"Failed to save PDF: {str(e)}")
            return None

    @with_context()
    def handle_document_save(self, sender_jid, message_data):
        """
        Handle saving document files for document conversion workflows.
        
        Args:
            sender_jid (str): The user's JID
            message_data (dict): The message data
            
        Returns:
            str: Saved filename if successful, None otherwise
        """
        # Get workflow instance for this user
        workflow_instance = self._get_workflow_instance(sender_jid)
        if not workflow_instance:
            logger.warning(f"Received document from user without active workflow: {sender_jid}")
            return None

        # Set context for consistent logging
        set_context(sender_jid=sender_jid, task_id=workflow_instance.task_id)
        
        # Extract message info
        message_id = message_data.get('key', {}).get('id')
        message_holder = message_data.get('message', {})
        base64_string = message_holder.get('base64')
        doc_message = message_holder.get('documentMessage', {})
        mimetype = doc_message.get('mimetype')
        filename = doc_message.get('fileName', f"{message_id}_file")
        
        if not all([message_id, base64_string]):
            logger.warning("Invalid document message format")
            return None

        # Determine file extension from mimetype or filename
        if '.' in filename:
            _, ext = os.path.splitext(filename)
        else:
            # Guess extension based on mimetype
            if 'word' in mimetype:
                ext = '.docx'
            elif 'powerpoint' in mimetype or 'presentation' in mimetype:
                ext = '.pptx'
            elif 'excel' in mimetype or 'sheet' in mimetype:
                ext = '.xlsx'
            else:
                ext = '.bin'  # generic binary file
        
        saved_filename = f"{message_id}{ext}"
        file_path = os.path.join(workflow_instance.task_dir, saved_filename)
        
        try:
            # Save document file
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(base64_string))

            logger.info(f"Saved document: {saved_filename}")
            
            # Store document message info in workflow state
            workflow_instance.state["document_message"] = doc_message
            
            # Let the workflow instance handle the file
            result, message = workflow_instance.handle_file_save(message_id, saved_filename)
            
            # Save updated workflow state
            self._save_workflow_instance(sender_jid, workflow_instance)
            
            # Send any response message to the user (if not already sent by the workflow)
            if message and self.whatsapp_client:
                self.whatsapp_client.send_text(sender_jid, message)
                
            return result

        except Exception as e:
            logger.error(f"Failed to save document: {str(e)}")
            return None
            
    @with_context()
    def handle_image_save(self, sender_jid, message_data):
        """
        Handle saving image files for scan workflow.
        
        Args:
            sender_jid (str): The user's JID
            message_data (dict): The message data
            
        Returns:
            str: Saved filename if successful, None otherwise
        """
        # Get workflow instance for this user
        workflow_instance = self._get_workflow_instance(sender_jid)
        if not workflow_instance:
            logger.warning(f"Received image from user without active workflow: {sender_jid}")
            return None

        # Set context for consistent logging
        set_context(sender_jid=sender_jid, task_id=workflow_instance.task_id)
        
        # Extract message info
        message_id = message_data.get('key', {}).get('id')
        message_holder = message_data.get('message', {})
        base64_string = message_holder.get('base64')
        img_message = message_holder.get('imageMessage', {})
        mimetype = img_message.get('mimetype')
        
        if not all([message_id, base64_string, mimetype.startswith('image/')]):
            logger.warning("Invalid image message format")
            return None

        # Determine file extension from mimetype
        if 'jpeg' in mimetype or 'jpg' in mimetype:
            ext = '.jpg'
        elif 'png' in mimetype:
            ext = '.png'
        else:
            ext = '.jpg'  # default to jpg
        
        saved_filename = f"{message_id}{ext}"
        file_path = os.path.join(workflow_instance.task_dir, saved_filename)
        
        try:
            # Save image file
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(base64_string))

            logger.info(f"Saved image: {saved_filename}")
            
            try:
                # Let the workflow instance handle the file - Use instance method directly
                result, message = workflow_instance.handle_image_save(message_id, saved_filename)
            except Exception as e:
                logger.error(f"Failed to save image: {str(e)}")
                return None
            
            # Save updated workflow state
            self._save_workflow_instance(sender_jid, workflow_instance)
            
            # Send any response message to the user (if not already sent by the workflow)
            if message and self.whatsapp_client:
                self.whatsapp_client.send_text(sender_jid, message)
                
            return result

        except Exception as e:
            logger.error(f"Failed to save image: {str(e)}")
            return None

    def _handle_workflow_command(self, sender_jid, message_text, quoted_stanza_id):
        """
        Handle workflow text commands.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
            quoted_stanza_id (str): ID of the quoted message (if any)
            
        Returns:
            bool: True if handled, False otherwise
        """
        # Get workflow instance for this user
        workflow_instance = self._get_workflow_instance(sender_jid)
        if not workflow_instance:
            return False
            
        # Set context for consistent logging
        set_context(sender_jid=sender_jid, task_id=workflow_instance.task_id)
        
        try:
            # Make sure we're using instance method, not static method
            workflow_class_name = workflow_instance.__class__.__name__
            task_dir = workflow_instance.task_dir
            
            # Use the proper method based on whether it's instance or static
            if hasattr(workflow_instance, 'handle_command') and callable(workflow_instance.handle_command):
                # Use instance method directly
                logger.debug(f"Using instance method handle_command for {workflow_class_name}")
                is_done, response_message = workflow_instance.handle_command(message_text, quoted_stanza_id)
            else:
                # Fallback to static method (should not happen after refactoring)
                logger.warning(f"Falling back to static handle_command for {workflow_class_name}")
                is_done, response_message = workflow_instance.__class__.handle_command(
                    task_dir, message_text, quoted_stanza_id, workflow_instance.state)
            
            # Save updated workflow state
            self._save_workflow_instance(sender_jid, workflow_instance)
            
            # Send response if any (if not already sent by the workflow)
            if response_message and self.whatsapp_client:
                self.whatsapp_client.send_text(sender_jid, response_message)
            
            # If workflow is done, finalize it
            if is_done:
                self._finalize_workflow(sender_jid)
                
            return True
        
        except Exception as e:
            logger.error(f"Error handling workflow command: {str(e)}", exc_info=True)
            if self.whatsapp_client:
                self.whatsapp_client.send_text(sender_jid, "Error processing your command. Please try again.")
            return True  # We still handled it, even though it errored
    
    def _finalize_workflow(self, sender_jid):
        """
        Finalize a workflow and send results to the user.
        
        Args:
            sender_jid (str): The user's JID
        """
        # Get workflow instance for this user
        workflow_instance = self._get_workflow_instance(sender_jid)
        if not workflow_instance:
            return
            
        # Set context for consistent logging
        set_context(sender_jid=sender_jid, task_id=workflow_instance.task_id)
        
        task_dir = workflow_instance.task_dir
        workflow_type = workflow_instance.__class__.__name__.replace("Workflow", "").lower()
        source_files = []  # Initialize with empty list
        output_files = []  # Initialize with empty list
        success = False
        error_message = None
        
        try:
            logger.info(f"Finalizing {workflow_type} workflow for user {sender_jid}")
            
            # Finalize the workflow and get output files
            output_files_paths = workflow_instance.finalize()
            
            # Convert output paths to format expected by cleanup_task_universal
            if output_files_paths:
                output_files = [{"path": path, "sent_id": os.path.basename(path)} for path in output_files_paths]
                
                # Find source files - we'll consider all PDF files that aren't in output_files
                try:
                    all_files = [f for f in os.listdir(task_dir) if f.endswith('.pdf')]
                    output_basenames = [os.path.basename(path) for path in output_files_paths]
                    source_files = [f for f in all_files if f not in output_basenames]
                    logger.debug(f"Found {len(source_files)} source files and {len(output_files)} output files")
                except Exception as e:
                    # Don't let file listing errors stop the workflow, just log them
                    logger.error(f"Error listing files in task directory: {str(e)}", exc_info=True)
            
            # Send output files to the user
            if output_files_paths and self.whatsapp_client:
                self.whatsapp_client.send_text(sender_jid, f"Task complete! Sending {len(output_files_paths)} file(s)...")
                
                # Create a mapping of file paths to display names
                display_names = {}
                
                # Handle file display names based on workflow type and original filenames
                for output_path in output_files_paths:
                    try:
                        output_basename = os.path.basename(output_path)
                        
                        # First, check if there's a display name in the original_filenames dictionary
                        # using the basename as the key (this is how split workflow stores them)
                        if 'original_filenames' in workflow_instance.state and output_basename in workflow_instance.state['original_filenames']:
                            display_names[output_path] = workflow_instance.state['original_filenames'][output_basename]
                            logger.info(f"Using display name from original_filenames for {output_basename}: {display_names[output_path]}")
                            continue
                            
                        # Try to extract message_id from filename
                        message_id = None
                        if '_compressed.pdf' in output_basename:
                            message_id = output_basename.split('_compressed.pdf')[0]
                        elif output_basename.endswith('.pdf'):
                            # For other workflows, try to get message ID from the filename
                            message_id = os.path.splitext(output_basename)[0]
                        
                        # If we found a message_id, try to get its original filename
                        if message_id and 'original_filenames' in workflow_instance.state:
                            orig_filename = workflow_instance.state['original_filenames'].get(message_id)
                            if orig_filename:
                                if workflow_type == 'compress':
                                    # For compression, add '_compressed' suffix to original filename
                                    basename, ext = os.path.splitext(orig_filename)
                                    display_names[output_path] = f"{basename}_compressed{ext}"
                                elif workflow_type in ['word_to_pdf', 'powerpoint_to_pdf', 'excel_to_pdf']:
                                    # For Office conversions, use original name with PDF extension
                                    basename, _ = os.path.splitext(orig_filename)
                                    display_names[output_path] = f"{basename}.pdf"
                                else:
                                    # For other workflows, use the original name as-is
                                    display_names[output_path] = orig_filename
                    except Exception as e:
                        # Don't let display name errors stop the workflow, just log them
                        logger.error(f"Error processing display name for {output_path}: {str(e)}")
                
                # Handle special workflows without message_id-based filenames
                try:
                    if workflow_type == 'scan':
                        # Generate timestamp-based names for scan workflow
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        
                        for i, output_path in enumerate(output_files_paths):
                            # Skip if we already have a display name from above
                            if output_path in display_names:
                                continue
                                
                            version_suffix = ""
                            basename = os.path.basename(output_path)
                            if "_BW" in basename:
                                version_suffix = "_BW"
                            elif "_magic_color" in basename:
                                version_suffix = "_enhanced"
                                
                            display_name = f"scanned_document{version_suffix}_{timestamp}.pdf"
                            if len(output_files_paths) > 1:
                                display_name = f"scanned_document{version_suffix}_{timestamp}_{i+1}.pdf"
                            
                            display_names[output_path] = display_name
                except Exception as e:
                    # Don't let scan workflow display name errors stop the process
                    logger.error(f"Error creating scan workflow display names: {str(e)}")
                
                # Send files with display names where available
                files_sent = 0
                for file_path in output_files_paths:
                    try:
                        if os.path.exists(file_path):
                            display_name = display_names.get(file_path)
                            if display_name:
                                logger.info(f"Sending {file_path} with display name: {display_name}")
                                self.whatsapp_client.send_media(sender_jid, file_path, filename=display_name)
                            else:
                                self.whatsapp_client.send_media(sender_jid, file_path)
                            files_sent += 1
                        else:
                            logger.warning(f"Output file does not exist: {file_path}")
                    except Exception as e:
                        logger.error(f"Error sending file {file_path}: {str(e)}", exc_info=True)
                
                if files_sent > 0:
                    success = True
                    self.whatsapp_client.send_text(sender_jid, f"Successfully sent {files_sent} file(s).")
                else:
                    error_message = "Failed to send output files."
                    logger.error(error_message)
            elif output_files_paths:
                # We have output files but no WhatsApp client
                logger.warning("Output files available but no WhatsApp client to send them")
                success = True
            else:
                error_message = "No output files were generated."
                logger.warning(error_message)
        
        except Exception as e:
            error_message = f"Error completing task: {str(e)}"
            logger.error(f"Error during workflow finalization: {str(e)}", exc_info=True)
        
        finally:
            # Send final status message to user
            if self.whatsapp_client:
                if error_message and not success:
                    self.whatsapp_client.send_text(sender_jid, error_message)
            
            # Always attempt to clean up, even if errors occurred
            try:
                cleanup_result, moved_count = cleanup_task_universal(task_dir, source_files, output_files)
                if not cleanup_result:
                    logger.warning(f"Cleanup completed with warnings. Moved {moved_count} files.")
                else:
                    logger.info(f"Cleanup completed successfully. Moved {moved_count} files.")
            except Exception as cleanup_error:
                logger.error(f"Error during task cleanup: {str(cleanup_error)}", exc_info=True)
            
            # Always delete workflow state, even if errors occurred
            try:
                self._delete_workflow_state(sender_jid)
                logger.info(f"Workflow state deleted for user {sender_jid}")
            except Exception as state_error:
                logger.error(f"Error deleting workflow state: {str(state_error)}", exc_info=True)

    @with_context()
    def handle_message(self, message_data):
        """
        Main handler for incoming messages.
        
        Args:
            message_data (dict): The message data
        """
        try:
            if 'data' not in message_data:
                return
                
            message_data = message_data['data']
            if message_data.get('key', {}).get('fromMe', False):
                return

            sender_jid = message_data.get('key', {}).get('remoteJid')
            message_id = message_data.get('key', {}).get('id')
            message_type = message_data.get('messageType')
            message_holder = message_data.get('message', {})
            
            # Get workflow instance if available
            workflow_instance = self._get_workflow_instance(sender_jid)
            
            # Set basic context for logging this message
            task_id = "no_task"
            if workflow_instance:
                task_id = workflow_instance.task_id
            
            set_context(sender_jid=sender_jid, task_id=task_id)
            logger.debug(f"Received message of type: {message_type}")
            
            # Extract context info (for quoted messages)
            context_info = message_data.get('contextInfo')
            if context_info is None and 'messageContextInfo' in message_holder:
                context_info = message_holder['messageContextInfo']
                
            quoted_stanza_id = context_info.get('stanzaId') if context_info and 'quotedMessage' in context_info else None

            # Extract message text
            message_text = None
            if message_type == 'conversation':
                message_text = message_holder.get('conversation', '').strip()
            elif message_type == 'extendedTextMessage':
                message_text = message_holder.get('extendedTextMessage', {}).get('text', '').strip()

            # Check if user is in an active workflow
            is_in_workflow = workflow_instance is not None
            
            # Handle workflow start commands
            if message_text and not is_in_workflow:
                command = message_text.lower()
                logger.info(f"Received command: {command}")
                
                workflow_commands = {
                    'merge pdf': 'merge',
                    'split pdf': 'split',
                    'scan document': 'scan',
                    'word to pdf': 'word_to_pdf',
                    'powerpoint to pdf': 'powerpoint_to_pdf',
                    'excel to pdf': 'excel_to_pdf',
                    'compress pdf': 'compress',
                    'markdown to pdf': 'markdown_to_pdf',
                    'markdown2 to pdf': 'markdown_to_pdf'  # Alias
                }
                
                if command in workflow_commands:
                    self.start_workflow(sender_jid, workflow_commands[command])
                    return
            
            # Handle active workflow interactions
            if is_in_workflow:
                workflow_type = workflow_instance.__class__.__name__.replace("Workflow", "").lower()
                logger.debug(f"Processing message for active workflow: {workflow_type}")

                # Handle PDF documents
                if message_type == 'documentMessage' and message_holder.get('documentMessage', {}).get('mimetype') == 'application/pdf' and 'base64' in message_holder:
                    logger.info("Received PDF document")
                    self.handle_pdf_save(sender_jid, message_data)
                    return

                # Handle image messages for scan workflow
                if message_type == 'imageMessage' and message_holder.get('imageMessage', {}).get('mimetype', '').startswith('image/') and 'base64' in message_holder:
                    logger.info("Received image for scanning")
                    self.handle_image_save(sender_jid, message_data)
                    return

                # Handle document messages for word_to_pdf workflow
                if message_type == 'documentMessage' and 'base64' in message_holder:
                    logger.info("Received document for processing")
                    self.handle_document_save(sender_jid, message_data)
                    return

                # Handle text commands for the active workflow
                if message_text:
                    self._handle_workflow_command(sender_jid, message_text, quoted_stanza_id)
                    return

        except Exception as e:
            logger.error(f"Error handling message: {str(e)}", exc_info=True)
            if 'sender_jid' in locals() and sender_jid and self.whatsapp_client:
                try:
                    self.whatsapp_client.send_text(sender_jid, "An internal error occurred processing your request.")
                except Exception:
                    pass
