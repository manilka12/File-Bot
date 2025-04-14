"""
Excel to PDF conversion workflow handler for the Document Scanner application.
"""

import os
import time
import logging
import subprocess
import shutil

from utils.file_utils import read_order_file, write_order_file

logger = logging.getLogger(__name__)

class ExcelToPdfWorkflow:
    """Handles the Excel to PDF conversion workflow."""
    
    @staticmethod
    def convert_excel_to_pdf_with_libreoffice(input_path, output_dir):
        """
        Convert Excel spreadsheet to PDF using LibreOffice with narrow margins.
        
        Args:
            input_path (str): Path to the Excel spreadsheet
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
            
            # Create a temporary macro to apply narrow margins and fit width
            macro_dir = os.path.join(abs_output_dir, "macro")
            os.makedirs(macro_dir, exist_ok=True)
            
            # Create a temporary excel file with adjusted settings
            temp_output_excel = os.path.join(abs_output_dir, f"temp_{input_filename}")
            
            # Create user profile directory to store custom settings
            user_profile_dir = os.path.join(abs_output_dir, "libreoffice_user_profile")
            os.makedirs(user_profile_dir, exist_ok=True)
            
            # First, copy the spreadsheet and set narrow margins using the soffice command
            logger.info(f"Creating a temporary Excel file with narrow margins: {temp_output_excel}")
            
            # Create settings file with narrow margins in user profile directory
            registrymodifications_file = os.path.join(user_profile_dir, "registrymodifications.xcu")
            with open(registrymodifications_file, "w") as f:
                f.write("""<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<item oor:path="/org.openoffice.Office.Calc/Print/Page/Margin"><prop oor:name="Left" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Page/Margin"><prop oor:name="Right" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Page/Margin"><prop oor:name="Top" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Page/Margin"><prop oor:name="Bottom" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Page"><prop oor:name="PageFormat" oor:op="fuse"><value>user</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Page"><prop oor:name="Orientation" oor:op="fuse"><value>landscape</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Page"><prop oor:name="Width" oor:op="fuse"><value>29700</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Page"><prop oor:name="Height" oor:op="fuse"><value>21000</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Scale"><prop oor:name="ScaleToPages" oor:op="fuse"><value>1</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Scale"><prop oor:name="ScaleToWidth" oor:op="fuse"><value>1</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Print/Scale"><prop oor:name="ScaleToHeight" oor:op="fuse"><value>0</value></prop></item>
</oor:items>""")
            
            # Method 1: Direct PDF export with minimal margins, landscape mode, and scaling
            logger.info("Converting Excel to PDF using direct export with minimal margins...")
            cmd = [
                'libreoffice',
                '--headless',
                f'-env:UserInstallation=file://{user_profile_dir}',
                '--convert-to', 'pdf:calc_pdf_Export:{"ScaleToWidth":1,"LeftMargin":0,"RightMargin":0,"TopMargin":0,"BottomMargin":0,"PageOrientation":1}',
                '--outdir', abs_output_dir,
                abs_input_path
            ]
            
            process = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=180  # 3 minutes timeout for large spreadsheets
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
            
            # Method 2: Try using unoconv if available (often provides better Excel conversion)
            logger.info("First method failed. Trying with unoconv if available...")
            try:
                # Check if unoconv is installed
                check_cmd = ["which", "unoconv"]
                check_process = subprocess.run(check_cmd, capture_output=True, text=True)
                
                if check_process.returncode == 0:
                    unoconv_cmd = [
                        "unoconv",
                        "-f", "pdf",
                        "-o", abs_output_dir,
                        "-P", "PaperOrientation=landscape",
                        "-P", "LeftMargin=0",
                        "-P", "RightMargin=0",
                        "-P", "TopMargin=0",
                        "-P", "BottomMargin=0",
                        "-P", "ScaleToWidth=1",
                        abs_input_path
                    ]
                    
                    unoconv_process = subprocess.run(
                        unoconv_cmd,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=180
                    )
                    
                    logger.info(f"unoconv process returned code: {unoconv_process.returncode}")
                    
                    # Check if the output file exists
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        logger.info(f"Successfully converted to PDF using unoconv: {output_path}")
                        return output_path
            except Exception as e:
                logger.warning(f"unoconv attempt failed: {str(e)}")
            
            # Method 3: Last resort - try using soffice with basic settings
            logger.info("Trying basic soffice command with standard settings...")
            cmd = [
                'soffice',
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
                timeout=180
            )
            
            # Check one last time
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"Successfully converted to PDF with basic soffice command: {output_path}")
                return output_path
            
            logger.error(f"PDF file not found or empty after all conversion attempts: {output_path}")
            return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"LibreOffice conversion timed out for: {input_path}")
            return None
        except Exception as e:
            logger.error(f"Error in Excel conversion: {str(e)}")
            return None
        finally:
            # Clean up any temporary files
            try:
                if 'user_profile_dir' in locals() and os.path.exists(user_profile_dir):
                    import shutil
                    shutil.rmtree(user_profile_dir, ignore_errors=True)
                if 'macro_dir' in locals() and os.path.exists(macro_dir):
                    import shutil
                    shutil.rmtree(macro_dir, ignore_errors=True)
                if 'temp_output_excel' in locals() and os.path.exists(temp_output_excel):
                    os.remove(temp_output_excel)
            except Exception as e:
                logger.warning(f"Error cleaning up temporary files: {str(e)}")
    
    @staticmethod
    def handle_spreadsheet_save(task_dir, message_id, saved_filename, workflow_info):
        """
        Handles saving and processing an Excel spreadsheet for conversion to PDF.
        
        Args:
            task_dir (str): Path to the task directory
            message_id (str): Message ID of the received spreadsheet
            saved_filename (str): Filename for the saved spreadsheet
            workflow_info (dict): Current workflow state
            
        Returns:
            tuple: (saved_filename, message) - Filename and message to send
        """
        file_path = os.path.join(task_dir, saved_filename)
        
        # Process the Excel spreadsheet
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
            
            # Check if it's an Excel spreadsheet
            if filename_ext.lower() not in ['.xls', '.xlsx', '.xlsm', '.xlsb', '.csv']:
                logger.warning(f"Not an Excel spreadsheet: {saved_filename}")
                return saved_filename, f"File {saved_filename} is not an Excel file. Please send a .xls, .xlsx, .xlsm, .xlsb, or .csv file."
            
            # Create PDF output filename using original name
            pdf_filename = f"{original_base}.pdf"
            pdf_path = os.path.join(task_dir, pdf_filename)
            
            logger.info(f"Converting Excel spreadsheet to PDF: {file_path}")
            
            # Convert Excel spreadsheet to PDF using LibreOffice
            output_pdf_path = ExcelToPdfWorkflow.convert_excel_to_pdf_with_libreoffice(file_path, task_dir)
            
            if output_pdf_path and os.path.exists(output_pdf_path):
                # If the converted PDF has a different name, rename it to use the original name
                if os.path.basename(output_pdf_path) != pdf_filename:
                    os.rename(output_pdf_path, pdf_path)
                    output_pdf_path = pdf_path
                
                logger.info(f"Successfully converted to PDF: {pdf_filename}")
                
                # Store the file references in workflow info
                if 'spreadsheet_versions' not in workflow_info:
                    workflow_info['spreadsheet_versions'] = {}
                
                workflow_info['spreadsheet_versions'][message_id] = {
                    'original': saved_filename,
                    'pdf': os.path.basename(output_pdf_path),
                    'original_name': original_filename
                }
                
                return saved_filename, f"Excel spreadsheet converted to PDF successfully. The PDF will be available when you type 'done'."
            else:
                logger.error(f"PDF conversion failed for {file_path}")
                return saved_filename, f"Sorry, I couldn't convert {saved_filename} to PDF. Please try again with a different file."
            
        except Exception as e:
            logger.error(f"Error converting Excel spreadsheet to PDF: {str(e)}")
            return saved_filename, f"Error converting spreadsheet: {str(e)}. Please try again with a different file."
    
    @staticmethod
    def finalize_task(task_dir, workflow_info):
        """
        Finalizes the Excel to PDF conversion task.
        
        Args:
            task_dir (str): Path to the task directory
            workflow_info (dict): Current workflow state
            
        Returns:
            list: List of created PDF paths
        """
        output_files = []
        
        try:
            # Check if we have any spreadsheets
            if 'spreadsheet_versions' not in workflow_info or not workflow_info['spreadsheet_versions']:
                logger.warning("No Excel spreadsheets received for conversion.")
                return []
            
            # Collect all PDF files
            for message_id, versions in workflow_info['spreadsheet_versions'].items():
                if 'pdf' in versions:
                    pdf_path = os.path.join(task_dir, versions['pdf'])
                    if os.path.exists(pdf_path):
                        output_files.append(pdf_path)
                        logger.info(f"Added PDF to result list: {versions['pdf']}")
                    else:
                        logger.warning(f"PDF file not found: {versions['pdf']}")
            
            # Create a merged PDF if multiple spreadsheets were converted
            if len(output_files) > 1:
                from pypdf import PdfReader, PdfWriter
                
                merged_pdf_path = os.path.join(task_dir, "Merged_Spreadsheets.pdf")
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
            logger.error(f"Error finalizing Excel to PDF task: {str(e)}")
            return output_files  # Return whatever we have even if there was an error