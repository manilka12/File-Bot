"""
Asynchronous task definitions for Document Scanner.

This module defines Celery tasks for long-running operations such as PDF compression,
document conversion, and scanning operations.
"""
import json
import os
import tempfile
import time
import logging
import subprocess
from typing import Dict, List, Any, Optional, Union
from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from app.celery_app import app, is_celery_available
from config.settings import CELERY_ENABLED, SCAN_VERSIONS
from utils.logging_utils import setup_logger, set_context, with_context
from utils.external_tools import (
    compress_pdf,
    convert_office_to_pdf,
    run_command,
    run_ghostscript
)
from utils.file_utils import check_file_exists_and_complete

# Set up the logger
logger = setup_logger(__name__)

class DocumentProcessingTask(Task):
    """Base class for document processing tasks with improved error handling."""
    
    abstract = True  # This is an abstract base class, not a concrete task
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(f"Task {task_id} failed: {exc}")
        super().on_failure(exc, task_id, args, kwargs, einfo)
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info(f"Task {task_id} completed successfully")
        super().on_success(retval, task_id, args, kwargs)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry."""
        logger.warning(f"Task {task_id} being retried due to: {exc}")
        super().on_retry(exc, task_id, args, kwargs, einfo)
        
    def __call__(self, *args, **kwargs):
        """Run the task with proper context setup."""
        task_id = self.request.id if hasattr(self, 'request') else "unknown"
        set_context(task_id=task_id, sender_jid="celery")
        
        try:
            logger.info(f"Starting task {self.name}[{task_id}]")
            start_time = time.time()
            result = super().__call__(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"Task {self.name}[{task_id}] completed in {elapsed:.2f} seconds")
            return result
        except SoftTimeLimitExceeded:
            logger.error(f"Task {self.name}[{task_id}] timed out")
            raise
        except Exception as e:
            logger.error(f"Task {self.name}[{task_id}] failed with error: {str(e)}", exc_info=True)
            raise


def execute_task(task_function, *args, **kwargs):
    """
    Execute a task either synchronously or asynchronously depending on Celery availability.
    
    Args:
        task_function: Celery task function
        *args, **kwargs: Arguments to pass to the task
        
    Returns:
        The task result or AsyncResult object
    """
    if CELERY_ENABLED and is_celery_available():
        # Execute asynchronously
        logger.info(f"Executing {task_function.__name__} asynchronously with Celery")
        return task_function.delay(*args, **kwargs)
    else:
        # Execute synchronously
        logger.info(f"Executing {task_function.__name__} synchronously (Celery disabled or unavailable)")
        return task_function(*args, **kwargs)


@shared_task(
    bind=True, 
    base=DocumentProcessingTask,
    max_retries=3,
    default_retry_delay=5,
    time_limit=300,  # 5 minutes
    soft_time_limit=270  # 4.5 minutes
)
def compress_pdf_task(self, input_path: str, output_path: str, dpi: int = 150, 
                      jpeg_quality: int = 80, pdfsettings: str = "/ebook") -> Dict[str, Any]:
    """
    Compress a PDF file asynchronously.
    
    Args:
        input_path: Path to the input PDF file
        output_path: Path to save the compressed PDF
        dpi: Resolution in DPI (lower means smaller file)
        jpeg_quality: JPEG quality (0-100, lower means smaller file)
        pdfsettings: Ghostscript PDF settings preset
        
    Returns:
        Dict containing compression results
    """
    try:
        logger.info(f"Compressing PDF: {input_path} -> {output_path}")
        
        # Check if input file exists and is valid
        if not check_file_exists_and_complete(input_path):
            return {
                "success": False,
                "error": f"Input file is missing or invalid: {input_path}"
            }
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Perform compression
        result = compress_pdf(
            input_path=input_path,
            output_path=output_path,
            dpi=dpi,
            jpeg_quality=jpeg_quality,
            pdfsettings=pdfsettings
        )
        
        # Verify output file exists and is valid
        if result.get("success", False):
            if not check_file_exists_and_complete(output_path):
                return {
                    "success": False,
                    "error": "Compression completed but output file is invalid"
                }
        
        return result
        
    except Exception as e:
        logger.error(f"Error compressing PDF: {str(e)}", exc_info=True)
        self.retry(exc=e, countdown=5)


@shared_task(
    bind=True, 
    base=DocumentProcessingTask,
    max_retries=3,
    default_retry_delay=5,
    time_limit=180,  # 3 minutes
    soft_time_limit=150  # 2.5 minutes
)
def convert_document_task(self, input_path: str, output_dir: str, 
                         doc_type: str = 'generic') -> Optional[str]:
    """
    Convert an Office document (Word, PowerPoint, Excel) to PDF asynchronously.
    
    Args:
        input_path: Path to the input document
        output_dir: Directory where the PDF should be saved
        doc_type: Document type ('word', 'powerpoint', 'excel', or 'generic')
        
    Returns:
        Path to the output PDF file if successful, None otherwise
    """
    try:
        logger.info(f"Converting {doc_type} document to PDF: {input_path}")
        
        # Check if input file exists and is valid
        if not check_file_exists_and_complete(input_path):
            logger.error(f"Input file is missing or invalid: {input_path}")
            return None
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Perform conversion
        output_path = convert_office_to_pdf(
            input_path=input_path,
            output_dir=output_dir,
            doc_type=doc_type
        )
        
        # Verify output file exists and is valid
        if output_path and not check_file_exists_and_complete(output_path):
            logger.error(f"Conversion completed but output file is invalid: {output_path}")
            return None
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error converting document: {str(e)}", exc_info=True)
        self.retry(exc=e, countdown=5)


@shared_task(
    bind=True, 
    base=DocumentProcessingTask,
    max_retries=2,
    default_retry_delay=5,
    time_limit=600,  # 10 minutes
    soft_time_limit=570  # 9.5 minutes
)
def merge_pdfs_task(self, input_files: List[str], output_path: str) -> bool:
    """
    Merge multiple PDF files asynchronously.
    
    Args:
        input_files: List of paths to input PDF files
        output_path: Path to save the merged PDF
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"Merging {len(input_files)} PDF files to {output_path}")
        
        # Check if input files exist and are valid
        for input_file in input_files:
            if not check_file_exists_and_complete(input_file):
                logger.error(f"Input file is missing or invalid: {input_file}")
                return False
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Prepare the gs command for merging PDFs
        gs_args = [
            "-sDEVICE=pdfwrite",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            f"-sOutputFile={output_path}"
        ] + input_files
        
        # Run ghostscript to merge the PDFs
        run_ghostscript(gs_args)
        
        # Verify output file exists and is valid
        if not check_file_exists_and_complete(output_path):
            logger.error(f"Merge completed but output file is invalid: {output_path}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error merging PDFs: {str(e)}", exc_info=True)
        self.retry(exc=e, countdown=5)


@shared_task(
    bind=True, 
    base=DocumentProcessingTask,
    max_retries=2,
    default_retry_delay=5,
    time_limit=300,  # 5 minutes
    soft_time_limit=270  # 4.5 minutes
)
def split_pdf_task(self, input_path: str, output_dir: str, page_ranges: List[Dict[str, int]]) -> List[str]:
    """
    Split a PDF file into multiple PDFs asynchronously.
    
    Args:
        input_path: Path to the input PDF file
        output_dir: Directory where the split PDFs should be saved
        page_ranges: List of dictionaries with 'start' and 'end' page numbers
        
    Returns:
        List of paths to the output PDF files
    """
    try:
        logger.info(f"Splitting PDF {input_path} into {len(page_ranges)} parts")
        
        # Check if input file exists and is valid
        if not check_file_exists_and_complete(input_path):
            logger.error(f"Input file is missing or invalid: {input_path}")
            return []
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        output_files = []
        for i, page_range in enumerate(page_ranges):
            start_page = page_range.get('start', 1)
            end_page = page_range.get('end', 1)
            
            # Create output filename
            output_file = os.path.join(output_dir, f"split_{i+1}_{start_page}-{end_page}.pdf")
            
            # Prepare the gs command for extracting pages
            gs_args = [
                "-sDEVICE=pdfwrite",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                f"-dFirstPage={start_page}",
                f"-dLastPage={end_page}",
                f"-sOutputFile={output_file}",
                input_path
            ]
            
            # Run ghostscript to extract the pages
            run_ghostscript(gs_args)
            
            # Verify output file exists and is valid
            if check_file_exists_and_complete(output_file):
                output_files.append(output_file)
            else:
                logger.error(f"Split part {i+1} failed: {output_file}")
        
        return output_files
        
    except Exception as e:
        logger.error(f"Error splitting PDF: {str(e)}", exc_info=True)
        self.retry(exc=e, countdown=5)


@shared_task(
    bind=True, 
    base=DocumentProcessingTask,
    max_retries=3,
    default_retry_delay=5,
    time_limit=600,  # 10 minutes
    soft_time_limit=570  # 9.5 minutes
)
def scan_image_task(self, image_path: str, output_dir: str) -> Dict[str, str]:
    """
    Process a scanned image using the document scanner.
    
    Args:
        image_path: Path to the input image file
        output_dir: Directory where the processed images should be saved
        
    Returns:
        Dict mapping version types to output filenames
    """
    try:
        logger.info(f"Processing scanned image: {image_path}")
        
        # Check if input file exists and is valid
        if not check_file_exists_and_complete(image_path):
            logger.error(f"Input file is missing or invalid: {image_path}")
            return {}
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get scanner path
        scanner_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
            'scanner', 
            'scanner.py'
        )
        
        # Run scanner on image
        logger.info(f"Running scanner on: {image_path}")
        process = subprocess.run(
            ['python', scanner_path, '--image', image_path, '--output', output_dir],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"Scanner output: {process.stdout}")
        if process.stderr:
            logger.warning(f"Scanner warnings: {process.stderr}")
        
        # Get message ID from filename
        filename = os.path.basename(image_path)
        message_id = os.path.splitext(filename)[0]
        
        # Build versions dictionary
        versions = {
            'original': filename,
            'bw': f"{message_id}_BW.jpg",
            'bw_direct': f"{message_id}_BW_direct.jpg",
            'magic_color': f"{message_id}_magic_color.jpg",
            'enhanced': f"{message_id}_magic_color_enhanced.png"
        }
        
        # Verify files exist
        for version_type, version_filename in versions.items():
            version_path = os.path.join(output_dir, version_filename)
            if os.path.exists(version_path):
                logger.info(f"{version_type} version saved: {version_filename}")
            else:
                logger.warning(f"{version_type} version not found: {version_filename}")
                
        return versions
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Scanner process failed: {str(e)}")
        logger.error(f"Scanner error output: {e.stderr}")
        self.retry(exc=e, countdown=5)
    except Exception as e:
        logger.error(f"Error processing scan: {str(e)}", exc_info=True)
        self.retry(exc=e, countdown=5)


@shared_task(
    bind=True, 
    base=DocumentProcessingTask,
    max_retries=3,
    default_retry_delay=5,
    time_limit=300,  # 5 minutes
    soft_time_limit=270  # 4.5 minutes
)
def create_pdf_from_images_task(self, image_paths: List[str], output_dir: str, versions=None) -> List[str]:
    """
    Create PDFs from processed images.
    
    Args:
        image_paths: List of paths to input images
        output_dir: Directory where the PDFs should be saved
        versions: List of version configurations
        
    Returns:
        List of paths to the created PDF files
    """
    try:
        logger.info(f"Creating PDFs from {len(image_paths)} images")
        
        # Use default versions if not specified
        if not versions:
            versions = SCAN_VERSIONS
        
        # Check if input files exist and are valid
        valid_images = []
        for image_path in image_paths:
            if check_file_exists_and_complete(image_path):
                valid_images.append(image_path)
            else:
                logger.warning(f"Input file is missing or invalid: {image_path}")
        
        if not valid_images:
            logger.error("No valid images provided")
            return []
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # For importing PIL and pypdf
        import io
        from PIL import Image
        from pypdf import PdfReader, PdfWriter
        
        output_files = []
        
        # Create PDF for each version type
        for version in versions:
            writer = PdfWriter()
            pdf_name = f"Scanned_Document_{version['name']}.pdf"
            output_path = os.path.join(output_dir, pdf_name)
            
            # Convert each image to PDF and append
            images_added = 0
            for image_filename in valid_images:
                # Extract message ID from filename
                base_filename = os.path.basename(image_filename)
                msg_id = os.path.splitext(base_filename)[0]
                
                # Get the right file based on version
                if version['name'] == 'original':
                    img_path = image_filename
                else:
                    # Construct path to processed image
                    img_path = os.path.join(output_dir, f"{msg_id}{version['suffix']}.jpg")
                
                # Skip if file doesn't exist
                if not os.path.exists(img_path):
                    logger.warning(f"Missing {version['name']} version for {msg_id}, skipping this image")
                    continue
                    
                # Convert image to PDF and add to writer
                try:
                    img = Image.open(img_path)
                    pdf_page = io.BytesIO()
                    img.save(pdf_page, format="PDF")
                    pdf_page.seek(0)
                    
                    reader = PdfReader(pdf_page)
                    writer.add_page(reader.pages[0])
                    images_added += 1
                    logger.info(f"Added {version['name']} version of {base_filename} to PDF")
                except Exception as e:
                    logger.error(f"Error adding {img_path} to PDF: {e}")
            
            # Only save the PDF if we added at least one image
            if images_added > 0:
                # Save the PDF
                try:
                    with open(output_path, "wb") as output_file:
                        writer.write(output_file)
                    
                    # Verify the output file is valid
                    if check_file_exists_and_complete(output_path):
                        output_files.append(output_path)
                        logger.info(f"Created PDF: {pdf_name} with {images_added} images")
                    else:
                        logger.error(f"Created PDF {pdf_name} is invalid")
                except Exception as e:
                    logger.error(f"Error writing PDF {pdf_name}: {e}")
        
        return output_files
        
    except Exception as e:
        logger.error(f"Error creating PDFs from images: {str(e)}", exc_info=True)
        self.retry(exc=e, countdown=5)


@app.task(bind=True, name="document_scanner.markdown_to_pdf")
def markdown_to_pdf_task(self, markdown_content: str, output_path: str, title: Optional[str] = None) -> Dict[str, Any]:
    """
    Celery task to convert markdown content to PDF.
    Tries multiple conversion methods with fallback.
    
    Args:
        markdown_content: Markdown text content to convert
        output_path: Path where to save the PDF output
        title: Optional title for the document
        
    Returns:
        Dict[str, Any]: Result information
    """
    logger.info(f"Starting markdown to PDF conversion task: {self.request.id}")
    output_dir = os.path.dirname(output_path)
    
    try:
        # Create a temporary markdown file with all the content
        with tempfile.NamedTemporaryFile(suffix='.md', mode='w', encoding='utf-8', dir=output_dir, delete=False) as temp:
            md_file_path = temp.name
            if title:
                temp.write(f"# {title}\n\n")
            temp.write(markdown_content)
        
        # Try method 1: md-to-pdf (ARM compatible)
        logger.info("Trying md-to-pdf method...")
        result = _convert_markdown_to_pdf_with_mdtopdf(md_file_path, output_path)
        
        if result["success"]:
            logger.info("md-to-pdf method succeeded")
            result["source_md"] = md_file_path
            # Clean up temp file
            try:
                os.unlink(md_file_path)
            except Exception:
                pass
            return result
                
        # If method 1 failed, try method 2: md2pdf/pandoc
        logger.info("md-to-pdf failed, trying md2pdf/pandoc method...")
        result = _convert_markdown_to_pdf_with_md2pdf(md_file_path, output_path)
        
        if result["success"]:
            logger.info(f"{result['method']} method succeeded")
            result["source_md"] = md_file_path
            # Clean up temp file
            try:
                os.unlink(md_file_path)
            except Exception:
                pass
            return result
        
        # If method 2 failed, try method 3: wkhtmltopdf
        logger.info("md2pdf/pandoc failed, trying wkhtmltopdf method...")
        result = _convert_markdown_to_pdf_with_wkhtmltopdf(md_file_path, output_path)
        
        if result["success"]:
            logger.info("wkhtmltopdf method succeeded")
            result["source_md"] = md_file_path
            # Clean up temp file
            try:
                os.unlink(md_file_path)
            except Exception:
                pass
            return result
        
        # If all methods failed
        logger.error("All markdown to PDF conversion methods failed")
        # Clean up temp file
        try:
            os.unlink(md_file_path)
        except Exception:
            pass
        return {
            "success": False,
            "error": "All markdown to PDF conversion methods failed"
        }
                
    except Exception as e:
        logger.error(f"Failed to convert markdown to PDF: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def _convert_markdown_to_pdf_with_mdtopdf(md_path: str, pdf_path: str) -> Dict[str, Any]:
    """
    Convert markdown to PDF using md-to-pdf (ARM-compatible).
    
    Args:
        md_path: Path to markdown file
        pdf_path: Output PDF path
        
    Returns:
        Dict[str, Any]: Result information
    """
    try:
        # Launch options for ARM compatibility
        launch_options = {
            "executablePath": "/usr/bin/chromium-browser",
            "args": ["--no-sandbox", "--disable-setuid-sandbox"]
        }
        
        # Construct the md-to-pdf command
        launch_options_str = json.dumps(launch_options)
        command = f"md-to-pdf --launch-options='{launch_options_str}' {md_path}"
        
        logger.info(f"Running command: {command}")
        
        # Execute the command with shell=True to preserve quotes
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            cwd=os.path.dirname(pdf_path)
        )
        
        if process.returncode != 0:
            logger.error(f"md-to-pdf error: {process.stderr}")
            return {
                "success": False,
                "error": process.stderr
            }
        
        # Check if PDF was created - md-to-pdf outputs to same filename with .pdf extension
        generated_pdf = f"{os.path.splitext(md_path)[0]}.pdf"
        if os.path.exists(generated_pdf):
            # Rename to expected output path if needed
            if generated_pdf != pdf_path:
                os.rename(generated_pdf, pdf_path)
            return {
                "success": True,
                "path": pdf_path,
                "method": "md-to-pdf"
            }
        else:
            return {
                "success": False,
                "error": "PDF file was not created"
            }
    except Exception as e:
        logger.error(f"Error in md-to-pdf conversion: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def _convert_markdown_to_pdf_with_md2pdf(md_path: str, pdf_path: str) -> Dict[str, Any]:
    """
    Convert markdown to PDF using md2pdf command-line tool with pandoc fallback.
    
    Args:
        md_path: Path to markdown file
        pdf_path: Output PDF path
        
    Returns:
        Dict[str, Any]: Result information
    """
    try:
        # Try md2pdf command-line tool first
        try:
            result = subprocess.run(
                ["md2pdf", md_path, pdf_path],
                capture_output=True,
                text=True,
                check=True
            )
            
            if os.path.exists(pdf_path):
                return {
                    "success": True,
                    "path": pdf_path,
                    "method": "md2pdf"
                }
            else:
                raise Exception("PDF file was not created by md2pdf")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"md2pdf command failed: {e.stderr}")
            # Try using pandoc as a fallback
            logger.warning("md2pdf command failed, trying pandoc as fallback...")
            
            pandoc_result = subprocess.run(
                ["pandoc", md_path, "-o", pdf_path],
                capture_output=True,
                text=True
            )
            
            if pandoc_result.returncode != 0:
                raise Exception(f"Pandoc conversion failed: {pandoc_result.stderr}")
            
            if os.path.exists(pdf_path):
                return {
                    "success": True,
                    "path": pdf_path,
                    "method": "pandoc"
                }
            else:
                raise Exception("PDF file was not created by pandoc")
            
    except Exception as e:
        logger.error(f"Failed to convert markdown to PDF with md2pdf/pandoc: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def _convert_markdown_to_pdf_with_wkhtmltopdf(md_path: str, pdf_path: str) -> Dict[str, Any]:
    """
    Convert markdown to PDF using wkhtmltopdf with markdown pre-processing.
    This method works better on ARM-based systems.
    
    Args:
        md_path: Path to markdown file
        pdf_path: Output PDF path
        
    Returns:
        Dict[str, Any]: Result information
    """
    try:
        # First convert markdown to HTML using Python's markdown module
        # Install it if not available
        try:
            import markdown
        except ImportError:
            logger.info("Installing markdown module...")
            subprocess.run(["pip", "install", "markdown"], check=True)
            import markdown
            
        # Read markdown content
        with open(md_path, 'r', encoding='utf-8') as md_file:
            md_content = md_file.read()
            
        # Convert to HTML
        html_content = markdown.markdown(
            md_content, 
            extensions=['tables', 'fenced_code', 'nl2br', 'codehilite']
        )
        
        # Add basic styling
        styled_html = f"""<!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Markdown Document</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 2em; max-width: 800px; }}
                h1 {{ color: #333366; }}
                h2 {{ color: #333366; border-bottom: 1px solid #eaecef; }}
                pre {{ background-color: #f6f8fa; padding: 16px; border-radius: 6px; }}
                code {{ font-family: Consolas, monospace; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; }}
                th {{ background-color: #f2f2f2; }}
                img {{ max-width: 100%; }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>"""
        
        # Save HTML to temp file
        html_path = os.path.join(os.path.dirname(pdf_path), "temp_markdown.html")
        with open(html_path, 'w', encoding='utf-8') as html_file:
            html_file.write(styled_html)
            
        # Convert HTML to PDF using wkhtmltopdf
        logger.info(f"Converting HTML to PDF using wkhtmltopdf...")
        subprocess.run([
            "wkhtmltopdf",
            "--enable-local-file-access",
            "--quiet",
            html_path,
            pdf_path
        ], check=True)
        
        # Check if PDF was created
        if os.path.exists(pdf_path):
            # Clean up temp HTML file
            os.remove(html_path)
            return {
                "success": True,
                "path": pdf_path,
                "method": "wkhtmltopdf"
            }
        else:
            return {
                "success": False,
                "error": "PDF file was not created by wkhtmltopdf"
            }
            
    except subprocess.CalledProcessError as e:
        logger.error(f"wkhtmltopdf command failed: {str(e)}")
        return {
            "success": False,
            "error": f"wkhtmltopdf command failed: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error in wkhtmltopdf conversion: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }