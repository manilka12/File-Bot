"""
PDF Merge workflow handler for the Document Scanner application.
"""

import os
import logging
import json
from pypdf import PdfWriter

from utils.file_utils import read_order_file, write_order_file

logger = logging.getLogger(__name__)

class MergeWorkflow:
    """Handles the PDF merge workflow."""
    
    @staticmethod
    def handle_pdf_save(task_dir, message_id, saved_filename):
        """
        Handles saving a PDF to the merge workflow's task directory.
        
        Args:
            task_dir (str): Path to the task directory
            message_id (str): Message ID of the received PDF
            saved_filename (str): Filename for the saved PDF
            
        Returns:
            str: The saved filename
        """
        order_data = read_order_file(task_dir)
        next_order = max(list(order_data.values()) + [0]) + 1
        order_data[saved_filename] = next_order
        write_order_file(task_dir, order_data)
        logger.info(f"Saved PDF {saved_filename} (order: {next_order})")
        return saved_filename
    
    @staticmethod
    def handle_order_override(task_dir, target_filename, new_order_str):
        """
        Handle order override for PDF merge workflow.
        
        Args:
            task_dir (str): Path to the task directory
            target_filename (str): Filename to reorder
            new_order_str (str): New order as string
            
        Returns:
            bool: True if successful, False if failed
            str: Message describing the result
        """
        order_data = read_order_file(task_dir)
        
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

        if write_order_file(task_dir, new_order_map):
            return True, f"Order updated. The file is now number {new_order}."
        else:
            return False, "Failed to update order file."
    
    @staticmethod
    def merge_pdfs_in_order(task_dir, order_data):
        """
        Merges PDFs based on order_data and saves as Merged_pdf.pdf.
        
        Args:
            task_dir (str): Path to the task directory
            order_data (dict): Dictionary mapping filenames to their order
            
        Returns:
            tuple: (output_path, missing_files)
        """
        output_filename = "Merged_pdf.pdf"
        output_path = os.path.join(task_dir, output_filename)
        merger = PdfWriter()
        merged_something = False
        missing_files = []

        sorted_files = sorted(order_data.items(), key=lambda item: item[1])
        logger.info(f"Merging {len(sorted_files)} PDFs")

        for filename, order in sorted_files:
            file_path = os.path.join(task_dir, filename)
            if os.path.exists(file_path):
                try:
                    merger.append(file_path)
                    merged_something = True
                except Exception as e:
                    logger.error(f"Error merging {filename}: {e}")
                    missing_files.append(f"{filename}")
            else:
                missing_files.append(filename)

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
            logger.info("Merge completed successfully")
            return output_path, []
        except Exception as e:
            logger.error(f"Error saving merged PDF: {str(e)}")
            merger.close()
            return None, []
