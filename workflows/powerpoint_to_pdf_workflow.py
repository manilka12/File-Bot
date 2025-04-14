"""
PowerPoint to PDF conversion workflow handler for the Document Scanner application.
"""

import os
import time
import logging
import subprocess
import shutil

from utils.file_utils import read_order_file, write_order_file

logger = logging.getLogger(__name__)

class PowerPointToPdfWorkflow:
    """Handles the PowerPoint to PDF conversion workflow."""
    
    @staticmethod
    def convert_ppt_to_pdf_with_libreoffice(input_path, output_dir):
        """
        Convert PowerPoint presentation to PDF using LibreOffice.
        
        Args:
            input_path (str): Path to the PowerPoint presentation
            output_dir (str): Directory where the PDF should be saved
            
        Returns:
            str: Path to the generated PDF or None if conversion failed
        """
        try:
            # Get absolute paths to ensure proper access
            abs_input_path = os.path.abspath(input_path)
            abs_output_dir = os.path.abspath(output_dir)
            
            # Ensure input file exists and has size > 0
            if not os.path.exists(abs_input_path) or os.path.getsize(abs_input_path) == 0:
                logger.error(f"Input file does not exist or is empty: {abs_input_path}")
                return None
                
            # Ensure output directory exists
            os.makedirs(abs_output_dir, exist_ok=True)
            
            # Get output filename
            input_filename = os.path.basename(abs_input_path)
            output_filename = os.path.splitext(input_filename)[0] + '.pdf'
            output_path = os.path.join(abs_output_dir, output_filename)
            
            # Run LibreOffice conversion
            logger.info(f"Converting PowerPoint to PDF using LibreOffice: {abs_input_path}")
            cmd = [
                'libreoffice',
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', abs_output_dir,
                abs_input_path
            ]
            
            process = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=180  # 3 minutes timeout for large presentations
            )
            
            logger.info(f"LibreOffice process returned code: {process.returncode}")
            
            if process.stdout:
                logger.info(f"LibreOffice output: {process.stdout}")
            
            if process.stderr:
                logger.warning(f"LibreOffice warnings: {process.stderr}")
            
            # Check if the output file exists
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"Successfully converted to PDF: {output_path}")
                return output_path
            else:
                logger.error(f"PDF file not found or empty after conversion: {output_path}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"LibreOffice conversion timed out for: {input_path}")
            return None
        except Exception as e:
            logger.error(f"Error in PowerPoint conversion: {str(e)}")
            return None
    
    @staticmethod
    def handle_presentation_save(task_dir, message_id, saved_filename, workflow_info):
        """
        Handles saving and processing a PowerPoint presentation for conversion to PDF.
        
        Args:
            task_dir (str): Path to the task directory
            message_id (str): Message ID of the received presentation
            saved_filename (str): Filename for the saved presentation
            workflow_info (dict): Current workflow state
            
        Returns:
            tuple: (saved_filename, message) - Filename and message to send
        """
        file_path = os.path.join(task_dir, saved_filename)
        
        # Process the PowerPoint presentation
        try:
            # Get file extension and original name from document message if available
            filename_base, filename_ext = os.path.splitext(saved_filename)
            
            # Try to get the original filename from the workflow_info
            original_filename = None
            if 'original_filenames' in workflow_info and message_id in workflow_info['original_filenames']:
                original_filename = workflow_info['original_filenames'][message_id]
            
            # If no original filename, use message_id as base
            if not original_filename:
                original_base = filename_base
            else:
                # Extract just the name part without extension
                original_base, _ = os.path.splitext(original_filename)
            
            # Check if it's a PowerPoint presentation
            if filename_ext.lower() not in ['.ppt', '.pptx', '.pps', '.ppsx']:
                logger.warning(f"Not a PowerPoint presentation: {saved_filename}")
                return saved_filename, f"File {saved_filename} is not a PowerPoint presentation. Please send a .ppt, .pptx, .pps, or .ppsx file."
            
            # Create PDF output filename using original name
            pdf_filename = f"{original_base}.pdf"
            pdf_path = os.path.join(task_dir, pdf_filename)
            
            logger.info(f"Converting PowerPoint presentation to PDF: {file_path}")
            
            # Convert PowerPoint presentation to PDF using LibreOffice
            output_pdf_path = PowerPointToPdfWorkflow.convert_ppt_to_pdf_with_libreoffice(file_path, task_dir)
            
            if output_pdf_path and os.path.exists(output_pdf_path):
                # If the converted PDF has a different name, rename it to use the original name
                if os.path.basename(output_pdf_path) != pdf_filename:
                    os.rename(output_pdf_path, pdf_path)
                    output_pdf_path = pdf_path
                
                logger.info(f"Successfully converted to PDF: {pdf_filename}")
                
                # Store the file references in workflow info
                if 'presentation_versions' not in workflow_info:
                    workflow_info['presentation_versions'] = {}
                
                workflow_info['presentation_versions'][message_id] = {
                    'original': saved_filename,
                    'pdf': os.path.basename(output_pdf_path),
                    'original_name': original_filename
                }
                
                return saved_filename, f"PowerPoint presentation converted to PDF successfully. The PDF will be available when you type 'done'."
            else:
                logger.error(f"PDF conversion failed for {file_path}")
                return saved_filename, f"Sorry, I couldn't convert {saved_filename} to PDF. Please try again with a different file."
            
        except Exception as e:
            logger.error(f"Error converting PowerPoint presentation to PDF: {str(e)}")
            return saved_filename, f"Error converting presentation: {str(e)}. Please try again with a different file."
    
    @staticmethod
    def finalize_task(task_dir, workflow_info):
        """
        Finalizes the PowerPoint to PDF conversion task.
        
        Args:
            task_dir (str): Path to the task directory
            workflow_info (dict): Current workflow state
            
        Returns:
            list: List of created PDF paths
        """
        output_files = []
        
        try:
            # Check if we have any presentations
            if 'presentation_versions' not in workflow_info or not workflow_info['presentation_versions']:
                logger.warning("No PowerPoint presentations received for conversion.")
                return []
            
            # Collect all PDF files
            for message_id, versions in workflow_info['presentation_versions'].items():
                if 'pdf' in versions:
                    pdf_path = os.path.join(task_dir, versions['pdf'])
                    if os.path.exists(pdf_path):
                        output_files.append(pdf_path)
                        logger.info(f"Added PDF to result list: {versions['pdf']}")
                    else:
                        logger.warning(f"PDF file not found: {versions['pdf']}")
            
            # Create a merged PDF if multiple presentations were converted
            if len(output_files) > 1:
                from pypdf import PdfReader, PdfWriter
                
                merged_pdf_path = os.path.join(task_dir, "Merged_Presentations.pdf")
                writer = PdfWriter()
                
                for pdf_path in output_files:
                    reader = PdfReader(pdf_path)
                    for page in reader.pages:
                        writer.add_page(page)
                
                with open(merged_pdf_path, "wb") as output_file:
                    writer.write(output_file)
                
                output_files.append(merged_pdf_path)
                logger.info(f"Created merged PDF: {merged_pdf_path}")
            
            return output_files
            
        except Exception as e:
            logger.error(f"Error finalizing PowerPoint to PDF task: {str(e)}")
            return output_files  # Return whatever we have even if there was an error