"""
Document Scan workflow handler for the Document Scanner application.
"""

import os
import time
import logging
import subprocess
import io
from PIL import Image
from pypdf import PdfReader, PdfWriter

from config.settings import SCAN_VERSIONS
from utils.file_utils import read_order_file, write_order_file

logger = logging.getLogger(__name__)

class ScanWorkflow:
    """Handles the document scan workflow."""
    
    @staticmethod
    def handle_image_save(task_dir, message_id, saved_filename, workflow_info):
        """
        Handles saving and processing an image for the scan workflow.
        
        Args:
            task_dir (str): Path to the task directory
            message_id (str): Message ID of the received image
            saved_filename (str): Filename for the saved image
            workflow_info (dict): Current workflow state
            
        Returns:
            tuple: (saved_filename, message) - Filename and message to send
        """
        file_path = os.path.join(task_dir, saved_filename)
        
        # Process the image with scanner.py
        try:
            # Call scanner program with correct python command
            # Fix: Use the absolute path to scanner.py in the Document-Scanner-Restructured directory
            scanner_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                      'scanner', 'scanner.py')
            
            logger.info(f"Running scanner on: {file_path}")
            process = subprocess.run(
                ['python', scanner_path, '--image', file_path, '--output', task_dir],
                check=True,
                capture_output=True,
                text=True
            )
            
            logger.info(f"Scanner output: {process.stdout}")
            if process.stderr:
                logger.warning(f"Scanner warnings: {process.stderr}")
            
            # Verify processed files exist
            versions = {
                'original': saved_filename,
                'bw': f"{message_id}_BW.jpg",
                'bw_direct': f"{message_id}_BW_direct.jpg",
                # Still track but temporarily disabled in PDF creation:
                'magic_color': f"{message_id}_magic_color.jpg",
                'enhanced': f"{message_id}_magic_color_enhanced.png"
            }
            
            # Add a waiting/checking mechanism to ensure B&W version is complete
            bw_file_path = os.path.join(task_dir, f"{message_id}_BW.jpg")
            max_wait_time = 30  # Maximum seconds to wait for BW processing
            wait_interval = 1   # Check every second
            wait_time = 0
            
            while wait_time < max_wait_time:
                if os.path.exists(bw_file_path):
                    # Check if file is fully written (not still being processed)
                    try:
                        with open(bw_file_path, "rb+") as f:
                            # If we can open the file for reading and writing, it's complete
                            break
                    except IOError:
                        pass
                
                time.sleep(wait_interval)
                wait_time += wait_interval
            
            # Check if processed files exist
            for version_type, version_filename in versions.items():
                version_path = os.path.join(task_dir, version_filename)
                if os.path.exists(version_path):
                    logger.info(f"{version_type} version saved: {version_filename}")
                else:
                    logger.warning(f"{version_type} version not found: {version_filename}")
            
            if 'image_versions' not in workflow_info:
                workflow_info['image_versions'] = {}
            workflow_info['image_versions'][message_id] = versions
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Scanner failed for {file_path}: {str(e)}")
            logger.error(f"Scanner error output: {e.stderr}")
        
        # Update order data
        order_data = read_order_file(task_dir) or {}  # Initialize if None
        next_order = max(list(order_data.values()) + [0]) + 1
        order_data[saved_filename] = next_order
        
        # Write order file
        if write_order_file(task_dir, order_data):
            logger.info(f"Updated order file with image {saved_filename} as number {next_order}")
        else:
            logger.error("Failed to write order file")

        return saved_filename, f"Image {next_order} received and processed. Send another or type 'done'."
    
    @staticmethod
    def handle_order_override(task_dir, target_filename, new_order_str):
        """
        Handle order override for scan workflow.
        
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
            return False, "Cannot reorder the quoted message. Please reply directly to an image sent for this task."

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
            return True, f"Order updated. The image is now number {new_order}."
        else:
            return False, "Failed to update order file."
    
    @staticmethod
    def create_pdfs_from_images(task_dir, order_data, versions=None):
        """
        Creates PDFs from processed images.
        
        Args:
            task_dir (str): Path to the task directory
            order_data (dict): Dictionary mapping filenames to their order
            versions (list): List of version configurations to process
            
        Returns:
            list: List of created PDF paths
        """
        if not versions:
            versions = SCAN_VERSIONS
            
        if not order_data:
            logger.warning("No images received for scanning.")
            return []

        # Get sorted images list
        sorted_images = sorted(order_data.items(), key=lambda x: x[1])
        output_files = []
        
        try:
            # Create PDF for each version type
            for version in versions:
                writer = PdfWriter()
                pdf_name = f"Scanned_Document_{version['name']}.pdf"
                output_path = os.path.join(task_dir, pdf_name)
                
                # Convert each image to PDF and append
                for image_filename, _ in sorted_images:
                    msg_id = image_filename.split('.')[0]
                    
                    # Get the right file based on version
                    if version['name'] == 'original':
                        img_path = os.path.join(task_dir, image_filename)
                    else:
                        img_path = os.path.join(task_dir, f"{msg_id}{version['suffix']}.jpg")
                    
                    # Skip if file doesn't exist
                    if not os.path.exists(img_path):
                        logger.warning(f"Missing {version['name']} version for {msg_id}, skipping this image")
                        continue
                        
                    # Convert image to PDF and add to writer
                    try:
                        img = Image.open(img_path)
                        img_width, img_height = img.size
                        pdf_page = io.BytesIO()
                        img.save(pdf_page, format="PDF")
                        pdf_page.seek(0)
                        
                        reader = PdfReader(pdf_page)
                        writer.add_page(reader.pages[0])
                        logger.info(f"Added {version['name']} version of {image_filename} to PDF")
                    except Exception as e:
                        logger.error(f"Error adding {img_path} to PDF: {e}")
                
                # Save the PDF
                try:
                    with open(output_path, "wb") as output_file:
                        writer.write(output_file)
                    output_files.append(output_path)
                    logger.info(f"Created PDF: {pdf_name}")
                except Exception as e:
                    logger.error(f"Error writing PDF {pdf_name}: {e}")
            
            return output_files
            
        except Exception as e:
            logger.error(f"Error creating PDFs from images: {str(e)}")
            return []
