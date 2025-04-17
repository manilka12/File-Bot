"""
Workflow for converting markdown text messages to PDF.
First tries md-to-pdf (ARM compatible), then falls back to md2pdf or pandoc.
"""

import os
import logging
import subprocess
import json
import tempfile
from datetime import datetime

# Initialize logger
logger = logging.getLogger(__name__)

class MarkdownToPdfWorkflow:
    """Handles markdown text to PDF conversion with fallback mechanisms."""
    
    @staticmethod
    def append_markdown_content(task_dir, message_id, text_content, workflow_info=None):
        """
        Appends markdown content to the collection.
        
        Args:
            task_dir (str): Task directory path
            message_id (str): Message ID
            text_content (str): Markdown text content
            workflow_info (dict): Workflow information
            
        Returns:
            tuple: (success, message)
        """
        if not workflow_info or workflow_info.get("workflow_type") != "markdown_to_pdf":
            return False, None
            
        # Initialize markdown content if not already present
        if "markdown_content" not in workflow_info:
            workflow_info["markdown_content"] = []
            workflow_info["message_ids"] = []
            
        # Add new content
        workflow_info["markdown_content"].append(text_content)
        workflow_info["message_ids"].append(message_id)
        
        # Create a message to acknowledge receipt
        msg_count = len(workflow_info["markdown_content"])
        return True, f"Markdown content received ({msg_count} message{'s' if msg_count > 1 else ''}). Send more markdown text or 'done' to generate PDF."
    
    @staticmethod
    def convert_markdown_to_pdf_with_mdtopdf(task_dir, md_path, pdf_path):
        """
        Convert markdown to PDF using md-to-pdf (ARM-compatible).
        
        Args:
            task_dir (str): Task directory path
            md_path (str): Path to markdown file
            pdf_path (str): Output PDF path
            
        Returns:
            dict: Result information
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
                cwd=task_dir
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
    
    @staticmethod
    def convert_markdown_to_pdf_with_md2pdf(task_dir, md_path, pdf_path):
        """
        Convert markdown to PDF using md2pdf command-line tool with pandoc fallback.
        
        Args:
            task_dir (str): Task directory path
            md_path (str): Path to markdown file
            pdf_path (str): Output PDF path
            
        Returns:
            dict: Result information
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
    
    @staticmethod
    def convert_markdown_to_pdf(task_dir, markdown_content, output_filename="output.pdf", title=None):
        """
        Convert markdown content to PDF using multiple methods with fallback.
        First tries md-to-pdf (ARM compatible), then falls back to md2pdf/pandoc.
        
        Args:
            task_dir (str): Task directory path
            markdown_content (str): Combined markdown content
            output_filename (str): Output PDF filename
            title (str): Document title
            
        Returns:
            dict: Result information
        """
        try:
            # Create a markdown file with all the content
            md_file_path = os.path.join(task_dir, "combined_content.md")
            with open(md_file_path, "w", encoding="utf-8") as md_file:
                if title:
                    md_file.write(f"# {title}\n\n")
                md_file.write(markdown_content)
            
            output_path = os.path.join(task_dir, output_filename)
            
            # Try method 1: md-to-pdf (ARM compatible)
            logger.info("Trying md-to-pdf method...")
            result = MarkdownToPdfWorkflow.convert_markdown_to_pdf_with_mdtopdf(
                task_dir, 
                md_file_path, 
                output_path
            )
            
            if result["success"]:
                logger.info("md-to-pdf method succeeded")
                result["source_md"] = md_file_path
                return result
                
            # If method 1 failed, try method 2: md2pdf/pandoc
            logger.info("md-to-pdf failed, trying md2pdf/pandoc method...")
            result = MarkdownToPdfWorkflow.convert_markdown_to_pdf_with_md2pdf(
                task_dir, 
                md_file_path, 
                output_path
            )
            
            if result["success"]:
                logger.info(f"{result['method']} method succeeded")
                result["source_md"] = md_file_path
                return result
            
            # If all methods failed
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
    
    @staticmethod
    def generate_pdf_from_messages(task_dir, workflow_info):
        """
        Generate a PDF from collected markdown messages.
        
        Args:
            task_dir (str): Task directory path
            workflow_info (dict): Workflow information containing markdown content
            
        Returns:
            dict: Result information
        """
        if "markdown_content" not in workflow_info or not workflow_info["markdown_content"]:
            return {
                "success": False,
                "error": "No markdown content available"
            }
            
        # Combine all markdown content with proper spacing
        combined_content = "\n\n".join(workflow_info["markdown_content"])
        
        # Generate timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"document_{timestamp}.pdf"
        
        # Convert the combined markdown to PDF (will try methods with fallback)
        return MarkdownToPdfWorkflow.convert_markdown_to_pdf(
            task_dir, 
            combined_content, 
            output_filename,
            title="Markdown Document"
        )