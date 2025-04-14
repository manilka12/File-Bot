"""
Workflow for converting markdown text messages to PDF.
"""

import os
import logging
import tempfile
import subprocess
from datetime import datetime

# Initialize logger
logger = logging.getLogger(__name__)

class MarkdownToPdfWorkflow:
    """Handles markdown text to PDF conversion."""
    
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
    def convert_markdown_to_pdf(task_dir, markdown_content, output_filename="output.pdf", title=None):
        """
        Convert markdown content to PDF using the md2pdf command-line tool.
        
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
            
            # Use md2pdf command-line tool to convert markdown to PDF
            try:
                # Run the md2pdf command-line tool
                result = subprocess.run(
                    ["md2pdf", md_file_path, output_path],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                if os.path.exists(output_path):
                    return {
                        "success": True,
                        "path": output_path,
                        "source_md": md_file_path
                    }
                else:
                    raise Exception("PDF file was not created by md2pdf")
                    
            except subprocess.CalledProcessError as e:
                logger.error(f"md2pdf command failed: {e.stderr}")
                # Try using pandoc as a fallback
                logger.warning("md2pdf command failed, trying pandoc as fallback...")
                
                pandoc_result = subprocess.run(
                    ["pandoc", md_file_path, "-o", output_path],
                    capture_output=True,
                    text=True
                )
                
                if pandoc_result.returncode != 0:
                    raise Exception(f"Pandoc conversion failed: {pandoc_result.stderr}")
                
                if os.path.exists(output_path):
                    return {
                        "success": True,
                        "path": output_path,
                        "source_md": md_file_path,
                        "method": "pandoc"
                    }
                else:
                    raise Exception("PDF file was not created by pandoc")
                
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
        
        # Convert the combined markdown to PDF
        return MarkdownToPdfWorkflow.convert_markdown_to_pdf(
            task_dir, 
            combined_content, 
            output_filename,
            title="Markdown Document"
        )