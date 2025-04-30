"""
File utility functions for the Document Scanner application.
"""

import os
import json
import shutil
import logging
import re
import uuid
import tempfile
from typing import Dict, List, Tuple, Any, Optional, Union, cast

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to ensure it doesn't contain unsafe characters.
    
    Args:
        filename (str): Filename to sanitize
        
    Returns:
        str: Sanitized filename
    """
    # Replace potentially dangerous characters with underscores
    sanitized = re.sub(r'[\\/*?:"<>|]', '_', filename)
    
    # Ensure the filename doesn't start with a dot or dash
    if sanitized and (sanitized[0] == '.' or sanitized[0] == '-'):
        sanitized = f"_" + sanitized[1:]
        
    # Limit the length of the filename
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:250] + ext
        
    return sanitized

def ensure_safe_path(base_dir: str, requested_path: str) -> str:
    """
    Ensure that a path is safely within a base directory.
    
    Args:
        base_dir (str): Base directory that should contain the path
        requested_path (str): Path to validate
        
    Returns:
        str: Absolute path that is guaranteed to be within base_dir
        
    Raises:
        ValueError: If the path would escape the base directory
    """
    # Normalize paths to absolute paths
    abs_base = os.path.abspath(base_dir)
    
    # Handle different path joining cases
    if os.path.isabs(requested_path):
        abs_path = os.path.abspath(requested_path)
    else:
        # Join with base and normalize
        abs_path = os.path.abspath(os.path.join(abs_base, requested_path))
    
    # Check if the path is within the base directory
    if not abs_path.startswith(abs_base):
        logger.error(f"Path traversal attempt detected: {requested_path} -> {abs_path} (outside {abs_base})")
        raise ValueError(f"Path would escape the base directory: {requested_path}")
    
    return abs_path

def safe_write_file(file_path: str, content: Union[str, bytes], mode: str = 'w') -> bool:
    """
    Safely write content to a file using a temporary file.
    
    Args:
        file_path (str): Path to the file to write
        content (str or bytes): Content to write
        mode (str): File open mode ('w' for text, 'wb' for binary)
        
    Returns:
        bool: True if successful, False otherwise
    """
    dir_path = os.path.dirname(file_path)
    
    try:
        # Ensure directory exists
        os.makedirs(dir_path, exist_ok=True)
        
        # Create a temporary file in the same directory
        temp_fd, temp_path = tempfile.mkstemp(dir=dir_path)
        
        try:
            # Write content to the temporary file
            with os.fdopen(temp_fd, mode) as f:
                f.write(content)
                
            # Move the temporary file to the target location (atomic operation)
            shutil.move(temp_path, file_path)
            logger.debug(f"Successfully wrote file: {file_path}")
            return True
        except Exception as e:
            # Clean up the temporary file if still exists
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            logger.error(f"Error writing file {file_path}: {str(e)}")
            return False
    except Exception as e:
        logger.error(f"Error preparing to write file {file_path}: {str(e)}")
        return False

def read_order_file(task_dir: str) -> Dict[str, Any]:
    """
    Reads the merge_order.json file.
    
    Args:
        task_dir (str): Path to the task directory
        
    Returns:
        dict: Order data from the file, or empty dict if file doesn't exist
    """
    order_file_path = os.path.join(task_dir, "merge_order.json")
    try:
        if os.path.exists(order_file_path):
            with open(order_file_path, 'r') as f:
                return cast(Dict[str, Any], json.load(f))
        return {}  # Return empty dict if file doesn't exist
    except Exception as e:
        logger.error(f"Error reading merge order file {order_file_path}: {str(e)}")
        return {}  # Return empty dict on error

def write_order_file(task_dir: str, order_data: Dict[str, Any]) -> bool:
    """
    Writes data to the merge_order.json file.
    
    Args:
        task_dir (str): Path to the task directory
        order_data (dict): Data to write to the file
        
    Returns:
        bool: True if successful, False if failed
    """
    order_file_path = os.path.join(task_dir, "merge_order.json")
    try:
        # Use safe_write_file to write the order file
        content = json.dumps(order_data, indent=4)
        return safe_write_file(order_file_path, content, 'w')
    except Exception as e:
        logger.error(f"Error writing merge order file {order_file_path}: {str(e)}")
        return False

def check_file_exists_and_complete(file_path: str, min_size: int = 10) -> bool:
    """
    Check if a file exists and is not empty or corrupted.
    
    Args:
        file_path (str): Path to the file to check
        min_size (int): Minimum size in bytes for the file to be considered valid
        
    Returns:
        bool: True if the file exists and is valid
    """
    try:
        if not os.path.isfile(file_path):
            logger.warning(f"File doesn't exist: {file_path}")
            return False
            
        # Check file size
        size = os.path.getsize(file_path)
        if size < min_size:
            logger.warning(f"File is too small (possibly corrupted): {file_path}, size: {size} bytes")
            return False
            
        # For PDF files, we could do additional checks here
        if file_path.lower().endswith('.pdf'):
            # Basic check - ensure file starts with %PDF
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(5)
                if not header.startswith(b'%PDF-'):
                    logger.warning(f"File is not a valid PDF: {file_path}")
                    return False
            except Exception as e:
                logger.error(f"Error checking PDF header: {str(e)}")
                return False
                
        return True
    except Exception as e:
        logger.error(f"Error checking file {file_path}: {str(e)}")
        return False

def create_unique_filename(directory: str, base_name: str, extension: str) -> str:
    """
    Create a unique filename in the given directory.
    
    Args:
        directory (str): Directory to create the file in
        base_name (str): Base name for the file
        extension (str): File extension (including dot)
        
    Returns:
        str: Unique file path
    """
    # Ensure directory exists
    os.makedirs(directory, exist_ok=True)
    
    # Sanitize the base name
    base_name = sanitize_filename(base_name)
    
    # First try with just the base name
    file_path = os.path.join(directory, f"{base_name}{extension}")
    
    # If the file exists, add a timestamp and UUID
    if os.path.exists(file_path):
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        file_path = os.path.join(directory, f"{base_name}_{timestamp}_{unique_id}{extension}")
    
    return file_path

def cleanup_task_universal(
    task_dir: str,
    source_files: List[str], 
    output_files: List[Dict[str, str]]
) -> Tuple[bool, int]:
    """
    Unified cleanup function for all workflows.
    
    Args:
        task_dir (str): Path to the task directory
        source_files (list): List of source files to move
        output_files (list): List of output files to move
        
    Returns:
        tuple: (success, moved_count)
    """
    sender_dir = os.path.dirname(task_dir)
    all_media_dir = os.path.join(sender_dir, "All-Media")
    moved_count = 0
    overall_success = True

    # Make sure All-Media directory exists
    try:
        os.makedirs(all_media_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create All-Media directory: {str(e)}")
        overall_success = False

    # Move source files - handle each file independently
    for filename in source_files:
        try:
            src = os.path.join(task_dir, filename)
            dst = os.path.join(all_media_dir, filename)
            if os.path.exists(src):
                shutil.move(src, dst)
                moved_count += 1
                logger.debug(f"Moved source file: {filename}")
        except Exception as e:
            logger.error(f"Failed to move source file {filename}: {str(e)}")
            overall_success = False

    # Move output files - handle each file independently
    for output in output_files:
        try:
            src = output["path"]
            filename = f"{output.get('sent_id', os.path.basename(src))}.pdf"
            dst = os.path.join(all_media_dir, filename)
            if os.path.exists(src):
                shutil.move(src, dst)
                moved_count += 1
                logger.debug(f"Moved output file: {os.path.basename(src)} -> {filename}")
        except Exception as e:
            logger.error(f"Failed to move output file {output.get('path')}: {str(e)}")
            overall_success = False

    # Remove task directory - attempt even if previous steps failed
    if os.path.exists(task_dir):
        try:
            shutil.rmtree(task_dir)
            logger.info(f"Removed task directory: {task_dir}")
        except Exception as e:
            logger.error(f"Failed to remove task directory {task_dir}: {str(e)}")
            overall_success = False
        
    return overall_success, moved_count

def get_file_extension_from_mimetype(mimetype: Optional[str]) -> str:
    """
    Get file extension from MIME type.
    
    Args:
        mimetype (str): MIME type
        
    Returns:
        str: File extension including the dot
    """
    import mimetypes
    
    if not mimetype:
        return '.bin'
    if mimetype == 'application/pdf':
        return '.pdf'
    guess = mimetypes.guess_extension(mimetype)
    return guess or '.bin'
