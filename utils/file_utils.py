"""
File utility functions for the Document Scanner application.
"""

import os
import json
import shutil
import logging

logger = logging.getLogger(__name__)

def read_order_file(task_dir):
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
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error reading merge order file {order_file_path}: {str(e)}")
        return {}

def write_order_file(task_dir, order_data):
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
        with open(order_file_path, 'w') as f:
            json.dump(order_data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error writing merge order file {order_file_path}: {str(e)}")
        return False

def cleanup_task_universal(task_dir, source_files, output_files):
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

    try:
        os.makedirs(all_media_dir, exist_ok=True)

        # Move source files
        for filename in source_files:
            src = os.path.join(task_dir, filename)
            dst = os.path.join(all_media_dir, filename)
            if os.path.exists(src):
                shutil.move(src, dst)
                moved_count += 1

        # Move output files
        for output in output_files:
            src = output["path"]
            filename = f"{output.get('sent_id', os.path.basename(src))}.pdf"
            dst = os.path.join(all_media_dir, filename)
            if os.path.exists(src):
                shutil.move(src, dst)
                moved_count += 1

        # Remove task directory
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir)
        
        return True, moved_count

    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        return False, moved_count

def get_file_extension_from_mimetype(mimetype):
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
