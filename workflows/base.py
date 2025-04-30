"""
Base abstract class for all workflow implementations.

This module defines the common interface that all workflow classes should implement.
"""

import abc
import logging
from typing import Dict, Any, Tuple, List, Optional

from utils.logging_utils import setup_logger

# Setup logger
logger = setup_logger(__name__)

class BaseWorkflow(abc.ABC):
    """
    Abstract base class for all document scanner workflows.
    
    This class defines the interface that all workflow implementations should follow.
    """
    
    def __init__(self, task_id: str, task_dir: str, sender_jid: str, whatsapp_client=None):
        """
        Initialize the workflow.
        
        Args:
            task_id: Task identifier
            task_dir: Task directory path
            sender_jid: User's JID
            whatsapp_client: WhatsApp client instance for sending messages
        """
        self.task_id = task_id
        self.task_dir = task_dir
        self.sender_jid = sender_jid
        self.whatsapp_client = whatsapp_client
        self.state = self.get_initial_state()
        logger.info(f"Initialized {self.__class__.__name__} for task {task_id}")
    
    @classmethod
    @abc.abstractmethod
    def get_instructions(cls) -> str:
        """
        Get the user instructions for this workflow.
        
        Returns:
            str: User instructions
        """
        pass
    
    @classmethod
    @abc.abstractmethod
    def get_initial_state(cls) -> Dict[str, Any]:
        """
        Get the initial state for this workflow.
        
        Returns:
            Dict[str, Any]: Initial workflow state
        """
        pass
    
    @abc.abstractmethod
    def handle_file_save(self, message_id: str, saved_filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Handle saving a file for this workflow.
        
        Args:
            message_id: Message ID of the file
            saved_filename: Filename of the saved file
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (filename, message)
        """
        pass
    
    @abc.abstractmethod
    def handle_command(self, message_text: str, quoted_stanza_id: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Handle a command for this workflow.
        
        Args:
            message_text: Message text (command)
            quoted_stanza_id: ID of the quoted message (if any)
            
        Returns:
            Tuple[bool, Optional[str]]: (is_done, message)
            - is_done: True if the workflow is complete
            - message: Optional message to send to the user
        """
        pass
    
    @abc.abstractmethod
    def finalize(self) -> List[str]:
        """
        Finalize the workflow and return the output files.
        
        Returns:
            List[str]: List of output file paths
        """
        pass
    
    def send_message(self, message: str) -> None:
        """
        Send a message to the user.
        
        Args:
            message: Message to send
        """
        if self.whatsapp_client and message:
            self.whatsapp_client.send_text(self.sender_jid, message)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert workflow state to a dictionary for persistence.
        
        Returns:
            Dict[str, Any]: Dictionary representation of workflow state
        """
        # Get class name and preserve underscores for workflow type compatibility
        class_name = self.__class__.__name__.replace("Workflow", "")
        workflow_type = ""
        
        # Insert underscores before uppercase letters (except the first one)
        for i, char in enumerate(class_name):
            if char.isupper() and i > 0:
                workflow_type += "_"
            workflow_type += char.lower()
        
        return {
            "task_id": self.task_id,
            "task_dir": self.task_dir,
            "workflow_type": workflow_type,
            **self.state
        }
    
    @classmethod
    def from_dict(cls, workflow_data: Dict[str, Any], whatsapp_client=None):
        """
        Create a workflow instance from a persisted dictionary.
        
        Args:
            workflow_data: Dictionary containing workflow data
            whatsapp_client: WhatsApp client instance
        
        Returns:
            BaseWorkflow: Workflow instance
        """
        task_id = workflow_data.get("task_id")
        task_dir = workflow_data.get("task_dir")
        sender_jid = workflow_data.get("sender_jid", "unknown")
        
        # Create the instance
        instance = cls(task_id, task_dir, sender_jid, whatsapp_client)
        
        # Update the instance state with any additional data
        for key, value in workflow_data.items():
            if key not in ["task_id", "task_dir", "workflow_type", "sender_jid"]:
                instance.state[key] = value
        
        return instance
    
    def store_original_filename(self, message_id: str, saved_filename: str) -> None:
        """
        Store the original filename for a received file.
        This method should be called by all workflows that need to track original filenames.
        
        Args:
            message_id: Message ID of the file
            saved_filename: Saved filename (usually message_id based)
        """
        # Extract the original filename from the document message if available
        document_message = self.state.get("document_message", {})
        original_filename = None
        
        if document_message:
            original_filename = document_message.get("fileName")
            
        # Store original filename for later reference
        if original_filename:
            if 'original_filenames' not in self.state:
                self.state['original_filenames'] = {}
                
            self.state['original_filenames'][message_id] = original_filename
            logger.info(f"Stored original filename for {message_id}: {original_filename}")
        else:
            logger.warning(f"No original filename found for message_id: {message_id}")
            
    def get_original_filename(self, message_id: str, default_basename: str = "document") -> str:
        """
        Get the original filename for a message ID, without extension.
        
        Args:
            message_id: Message ID of the file
            default_basename: Default basename if no original filename is found
            
        Returns:
            str: Original filename without extension, or default_basename if not found
        """
        original_filename = None
        
        # First check if we have it in original_filenames
        if 'original_filenames' in self.state and message_id in self.state['original_filenames']:
            original_filename = self.state['original_filenames'][message_id]
            # Extract just the base name without extension
            import os
            original_basename = os.path.splitext(original_filename)[0]
            return original_basename
            
        # If not found, return default
        return default_basename
        
    def create_output_filename(self, message_id: str, extension: str = ".pdf", suffix: str = "", default_name: str = "document") -> str:
        """
        Create an output filename based on original filename.
        
        Args:
            message_id: Message ID of the original file
            extension: File extension (including dot)
            suffix: Optional suffix to add before extension (e.g., "_converted")
            default_name: Default basename if no original filename is found
            
        Returns:
            str: Output filename
        """
        # Get original basename or default
        basename = self.get_original_filename(message_id, default_name)
        
        # Create output filename
        return f"{basename}{suffix}{extension}"