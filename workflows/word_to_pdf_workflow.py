"""
Word to PDF conversion workflow handler for the Document Scanner application.
"""

import os
import time
import logging
import subprocess
import shutil

# Removed docx2pdf import since we'll use LibreOffice instead

from utils.file_utils import read_order_file, write_order_file

logger = logging.getLogger(__name__)

class WordToPdfWorkflow:
    """Handles the Word document to PDF conversion workflow."""
    
    @staticmethod
    def convert_word_to_pdf_with_libreoffice(input_path, output_dir):
        """
        Convert Word document to PDF using LibreOffice.
        
        Args:
            input_path (str): Path to the Word document
            output_dir (str): Directory where the PDF should be saved
            
        Returns:
            str: Path to the generated PDF or None if conversion failed
        """
        try:
            # Create a command to use LibreOffice in headless mode for conversion
            cmd = [
                'libreoffice', 
                '--headless', 
                '--convert-to', 'pdf', 
                '--outdir', output_dir,
                input_path
            ]
            
            # Execute the command
            process = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            
            # Get the output filename
            input_filename = os.path.basename(input_path)
            output_filename = os.path.splitext(input_filename)[0] + '.pdf'
            output_path = os.path.join(output_dir, output_filename)
            
            if os.path.exists(output_path):
                logger.info(f"Successfully converted {input_path} to {output_path}")
                return output_path
            else:
                logger.error(f"PDF file not found after conversion: {output_path}")
                logger.error(f"LibreOffice output: {process.stdout}")
                logger.error(f"LibreOffice error: {process.stderr}")
                return None
                
        except subprocess.CalledProcessError as e:
            logger.error(f"LibreOffice conversion failed: {e}")
            logger.error(f"LibreOffice output: {e.stdout}")
            logger.error(f"LibreOffice error: {e.stderr}")
            return None
        except Exception as e:
            logger.error(f"Error in LibreOffice conversion: {str(e)}")
            return None
    
    @staticmethod
    def handle_document_save(task_dir, message_id, saved_filename, workflow_info):
        """
        Handles saving and processing a Word document for conversion to PDF.
        
        Args:
            task_dir (str): Path to the task directory
            message_id (str): Message ID of the received document
            saved_filename (str): Filename for the saved document
            workflow_info (dict): Current workflow state
            
        Returns:
            tuple: (saved_filename, message) - Filename and message to send
        """
        file_path = os.path.join(task_dir, saved_filename)
        
        # Process the Word document
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
            
            # Check if it's a Word document
            if filename_ext.lower() not in ['.doc', '.docx']:
                logger.warning(f"Not a Word document: {saved_filename}")
                return saved_filename, f"File {saved_filename} is not a Word document. Please send a .doc or .docx file."
            
            # Create PDF output filename using original name
            pdf_filename = f"{original_base}.pdf"
            pdf_path = os.path.join(task_dir, pdf_filename)
            
            logger.info(f"Converting Word document to PDF: {file_path}")
            
            # Convert Word document to PDF using LibreOffice
            output_pdf_path = WordToPdfWorkflow.convert_word_to_pdf_with_libreoffice(file_path, task_dir)
            
            if output_pdf_path and os.path.exists(output_pdf_path):
                # If the converted PDF has a different name, rename it to use the original name
                if os.path.basename(output_pdf_path) != pdf_filename:
                    os.rename(output_pdf_path, pdf_path)
                    output_pdf_path = pdf_path
                
                logger.info(f"Successfully converted to PDF: {pdf_filename}")
                
                # Store the file references in workflow info
                if 'document_versions' not in workflow_info:
                    workflow_info['document_versions'] = {}
                
                workflow_info['document_versions'][message_id] = {
                    'original': saved_filename,
                    'pdf': os.path.basename(output_pdf_path),
                    'original_name': original_filename
                }
                
                return saved_filename, f"Word document converted to PDF successfully. The PDF will be available when you type 'done'."
            else:
                logger.error(f"PDF conversion failed for {file_path}")
                return saved_filename, f"Sorry, I couldn't convert {saved_filename} to PDF. Please try again with a different file."
            
        except Exception as e:
            logger.error(f"Error converting Word document to PDF: {str(e)}")
            return saved_filename, f"Error converting document: {str(e)}. Please try again with a different file."
    
    @staticmethod
    def finalize_task(task_dir, workflow_info):
        """
        Finalizes the Word to PDF conversion task.
        
        Args:
            task_dir (str): Path to the task directory
            workflow_info (dict): Current workflow state
            
        Returns:
            list: List of created PDF paths
        """
        output_files = []
        
        try:
            # Check if we have any documents
            if 'document_versions' not in workflow_info or not workflow_info['document_versions']:
                logger.warning("No documents received for conversion.")
                return []
            
            # Collect all PDF files
            for message_id, versions in workflow_info['document_versions'].items():
                if 'pdf' in versions:
                    pdf_path = os.path.join(task_dir, versions['pdf'])
                    if os.path.exists(pdf_path):
                        output_files.append(pdf_path)
                        logger.info(f"Added PDF to result list: {versions['pdf']}")
                    else:
                        logger.warning(f"PDF file not found: {versions['pdf']}")
            
            # Create a merged PDF if multiple documents were converted
            if len(output_files) > 1:
                from pypdf import PdfReader, PdfWriter
                
                merged_pdf_path = os.path.join(task_dir, "Merged_Documents.pdf")
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
            logger.error(f"Error finalizing Word to PDF task: {str(e)}")
            return output_files  # Return whatever we have even if there was an error