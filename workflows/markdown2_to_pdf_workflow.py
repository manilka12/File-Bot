"""
Workflow for converting PDF files to Markdown text using vb64/markdown-pdf.
This is a complete replacement of the previous implementation.
"""

import os
import logging
from datetime import datetime

# Initialize logger
logger = logging.getLogger(__name__)

class Markdown2ToPdfWorkflow:
    """Handles PDF to Markdown conversion using the vb64/markdown-pdf library."""
    
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
        if not workflow_info or workflow_info.get("workflow_type") != "markdown2_to_pdf":
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
        return True, f"Markdown content received ({msg_count} message{'s' if msg_count > 1 else ''}). Send more markdown text or 'done' to process PDF files."
    
    @staticmethod
    def pdf_to_markdown(task_dir, pdf_filename):
        """
        Convert a PDF file to Markdown text using vb64/markdown-pdf.
        
        Args:
            task_dir (str): Task directory path
            pdf_filename (str): PDF filename (not the path)
            
        Returns:
            dict: Result information with success status, output path, and content
        """
        try:
            # Import markdown-pdf
            try:
                import markdown_pdf
            except ImportError:
                logger.error("Failed to import vb64/markdown-pdf. Make sure it's installed.")
                return {
                    "success": False,
                    "error": "markdown-pdf library not installed. Please install with: pip install git+https://github.com/vb64/markdown-pdf.git"
                }
            
            # Set paths
            pdf_path = os.path.join(task_dir, pdf_filename)
            md_filename = os.path.splitext(pdf_filename)[0] + ".md"
            md_path = os.path.join(task_dir, md_filename)
            
            logger.info(f"Converting PDF to Markdown: {pdf_path}")
            
            # Convert PDF to Markdown
            markdown_content = markdown_pdf.pdf_to_markdown(pdf_path)
            
            # Write markdown to file
            with open(md_path, "w", encoding="utf-8") as md_file:
                md_file.write(markdown_content)
            
            return {
                "success": True,
                "path": md_path,
                "content": markdown_content
            }
            
        except Exception as e:
            logger.error(f"Error in PDF to Markdown conversion: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def generate_pdf_from_messages(task_dir, workflow_info):
        """
        Process PDF files using the markdown_pdf library.
        
        Args:
            task_dir (str): Task directory path
            workflow_info (dict): Workflow information
            
        Returns:
            dict: Result information
        """
        try:
            # Find all PDF files in the task directory
            pdf_files = [f for f in os.listdir(task_dir) if f.endswith('.pdf')]
            
            if not pdf_files:
                # Write the markdown content to a file if no PDFs were found
                combined_content = "\n\n".join(workflow_info.get("markdown_content", []))
                md_file_path = os.path.join(task_dir, "combined_content.md")
                
                with open(md_file_path, "w", encoding="utf-8") as md_file:
                    md_file.write(combined_content)
                
                return {
                    "success": True,
                    "message": "No PDF files found. Markdown content saved.",
                    "path": md_file_path,
                    "method": "direct_save",
                    "all_paths": {"direct_save": md_file_path},
                    "all_methods": ["direct_save"]
                }
            
            # Process all PDF files
            results = {}
            methods = []
            
            for pdf_file in pdf_files:
                result = Markdown2ToPdfWorkflow.pdf_to_markdown(task_dir, pdf_file)
                if result["success"]:
                    pdf_name = os.path.splitext(pdf_file)[0]
                    results[f"vb64_markdown_pdf_{pdf_name}"] = result["path"]
                    methods.append(f"vb64_markdown_pdf_{pdf_name}")
            
            # Return the results
            if results:
                # Get the first result as the primary one
                primary_method = methods[0]
                primary_path = results[primary_method]
                
                return {
                    "success": True,
                    "path": primary_path,
                    "method": primary_method,
                    "all_paths": results,
                    "all_methods": methods
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to convert any PDFs to Markdown"
                }
                
        except Exception as e:
            logger.error(f"Error processing PDFs with markdown_pdf: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }