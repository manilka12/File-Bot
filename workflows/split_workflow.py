"""
PDF Split workflow handler for the Document Scanner application.
"""

import os
import re
import logging
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

class SplitWorkflow:
    """Handles the PDF split workflow."""
    
    @staticmethod
    def handle_pdf_save(task_dir, message_id, saved_filename, workflow_info):
        """
        Handles saving a PDF to the split workflow's task directory.
        
        Args:
            task_dir (str): Path to the task directory
            message_id (str): Message ID of the received PDF
            saved_filename (str): Filename for the saved PDF
            workflow_info (dict): Current workflow state
            
        Returns:
            tuple: (saved_filename, message) - Filename and message to send
        """
        if workflow_info.get("split_files"):
            return None, "PDF already received. Reply to it with page ranges or start new task."
        
        workflow_info["split_files"] = {message_id: saved_filename}
        logger.info(f"Saved PDF for splitting: {saved_filename}")
        return saved_filename, "PDF received. Reply to it with page ranges (e.g., '1-10, 15, 20-25')"
    
    @staticmethod
    def parse_page_ranges(text_input, max_pages):
        """
        Parses user input for page ranges (e.g., '1-10', '15', '20-25').
        
        Args:
            text_input (str): Text containing page ranges
            max_pages (int): Maximum page number
            
        Returns:
            tuple: (ranges, error_message)
        """
        ranges = []
        raw_parts = re.split(r'[,\n\s]+', text_input)  # Split by comma, newline, or space

        for part in raw_parts:
            part = part.strip()
            if not part: continue
            if '-' in part:  # Range
                try:
                    start_str, end_str = part.split('-', 1)
                    start = int(start_str); end = int(end_str)
                    if 1 <= start <= end <= max_pages: 
                        ranges.append((start, end))
                    else: 
                        return None, f"Invalid range '{part}'. Pages must be between 1 and {max_pages}."
                except ValueError: 
                    return None, f"Invalid range format '{part}'. Use start-end."
            else:  # Single page
                try:
                    page = int(part)
                    if 1 <= page <= max_pages: 
                        ranges.append((page, page))  # Represent single page as a range
                    else: 
                        return None, f"Invalid page number '{part}'. Must be between 1 and {max_pages}."
                except ValueError: 
                    return None, f"Invalid page format '{part}'. Use numbers or ranges."

        if not ranges: return [], None  # No valid ranges found is okay here

        # Sort ranges by start page and merge overlapping/adjacent ones
        ranges.sort(key=lambda x: x[0])
        merged = []
        if ranges:
            current_start, current_end = ranges[0]
            for next_start, next_end in ranges[1:]:
                if next_start <= current_end + 1: 
                    current_end = max(current_end, next_end)
                else: 
                    merged.append((current_start, current_end))
                    current_start, current_end = next_start, next_end
            merged.append((current_start, current_end))
        
        logger.info(f"Parsed and merged requested ranges: {merged}")
        return merged, None
    
    @staticmethod
    def generate_split_definitions(requested_ranges, total_pages):
        """
        Generates all final split ranges, including the gaps.
        
        Args:
            requested_ranges (list): List of requested page ranges
            total_pages (int): Total number of pages
            
        Returns:
            list: List of dictionaries with split definitions
        """
        if not requested_ranges: return []
        
        all_splits = []
        current_page = 1
        requested_ranges.sort(key=lambda x: x[0])  # Ensure sorted
        
        for req_start, req_end in requested_ranges:
            if current_page < req_start:  # Add gap before
                all_splits.append({
                    "start": current_page, 
                    "end": req_start - 1, 
                    "requested": False
                })
            all_splits.append({
                "start": req_start, 
                "end": req_end, 
                "requested": True
            })  # Add requested
            current_page = req_end + 1
            
        if current_page <= total_pages:  # Add final gap
            all_splits.append({
                "start": current_page, 
                "end": total_pages, 
                "requested": False
            })
            
        return [s for s in all_splits if s["start"] <= s["end"]]  # Ensure validity
    
    @staticmethod
    def perform_split(task_dir, source_pdf_filename, split_definitions):
        """
        Splits the source PDF based on definitions and saves output files.
        
        Args:
            task_dir (str): Path to the task directory
            source_pdf_filename (str): Filename of the PDF to split
            split_definitions (list): List of dictionaries with split definitions
            
        Returns:
            list: List of output files with their paths and page ranges
        """
        source_pdf_path = os.path.join(task_dir, source_pdf_filename)
        output_files = []  # List to store paths of created split files
        
        try:
            reader = PdfReader(source_pdf_path)
            source_base_name = os.path.splitext(source_pdf_filename)[0]
            
            for split in split_definitions:
                start_page = split["start"]
                end_page = split["end"]
                writer = PdfWriter()
                pages_added = 0
                
                for page_num_zero_based in range(start_page - 1, end_page):
                    try: 
                        writer.add_page(reader.pages[page_num_zero_based])
                        pages_added += 1
                    except IndexError: 
                        break  # Stop adding for this range if error
                        
                if pages_added > 0:
                    output_filename = f"{source_base_name}_pages_{start_page}-{end_page}.pdf"
                    output_path = os.path.join(task_dir, output_filename)
                    
                    try:
                        with open(output_path, "wb") as f_out: 
                            writer.write(f_out)
                        output_files.append({
                            "path": output_path, 
                            "range": f"{start_page}-{end_page}"
                        })
                    except Exception as e: 
                        logger.error(f"Error writing split file {output_filename}: {str(e)}")
                        
            return output_files
            
        except Exception as e: 
            logger.error(f"Error during PDF splitting process for {source_pdf_path}: {str(e)}")
            return []
