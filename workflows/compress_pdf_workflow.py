"""
Workflow for compressing PDF files to reduce file size while maintaining quality.
"""

import os
import logging
import subprocess
from utils.file_utils import read_order_file

# Initialize logger
logger = logging.getLogger(__name__)

class CompressPdfWorkflow:
    """Handles PDF file compression."""
    
    # Compression levels with their Ghostscript settings
    COMPRESSION_LEVELS = {
        "low": {
            "dpi": 150,
            "color_profile": "sRGB",
            "colorspace": "srgb",
            "quality": 90,
            "description": "Low compression (good quality, moderate size reduction)"
        },
        "medium": {
            "dpi": 120,
            "color_profile": "sRGB",
            "colorspace": "srgb", 
            "quality": 80,
            "description": "Medium compression (balanced quality and size)"
        },
        "high": {
            "dpi": 96,
            "color_profile": "sRGB",
            "colorspace": "srgb",
            "quality": 70,
            "description": "High compression (smaller file size, adequate quality)"
        },
        "max": {
            "dpi": 72,
            "color_profile": "sRGB", 
            "colorspace": "srgb",
            "quality": 60,
            "description": "Maximum compression (smallest file size, lower quality)"
        }
    }
    
    @staticmethod
    def handle_pdf_save(task_dir, message_id, saved_filename, workflow_info=None):
        """
        Handle the saving of a PDF file for compression.
        
        Args:
            task_dir (str): Task directory path
            message_id (str): Message ID
            saved_filename (str): Saved filename
            workflow_info (dict): Workflow information
            
        Returns:
            tuple: (filename, message)
        """
        if not workflow_info or workflow_info.get("workflow_type") != "compress":
            return saved_filename, None
            
        pdf_file_path = os.path.join(task_dir, saved_filename)
        
        if not os.path.exists(pdf_file_path):
            return None, "Error: PDF file not found."
            
        # Store info about this PDF in the workflow
        if "compress_files" not in workflow_info:
            workflow_info["compress_files"] = {}
            
        workflow_info["compress_files"][message_id] = saved_filename
        
        # Get original file size for later comparison
        file_size_kb = os.path.getsize(pdf_file_path) / 1024
        workflow_info["original_sizes"] = workflow_info.get("original_sizes", {})
        workflow_info["original_sizes"][message_id] = file_size_kb
        
        return saved_filename, f"PDF received: {saved_filename} ({file_size_kb:.1f} KB). Send 'low', 'medium', 'high', or 'max' to set compression level, or 'auto' for automatic compression."
    
    @staticmethod
    def compress_pdf(input_path, output_path, compression_level="medium"):
        """
        Compress a PDF file using Ghostscript.
        
        Args:
            input_path (str): Path to input PDF
            output_path (str): Path to save compressed PDF
            compression_level (str): Compression level (low, medium, high, max)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get compression settings
            level_settings = CompressPdfWorkflow.COMPRESSION_LEVELS.get(
                compression_level, 
                CompressPdfWorkflow.COMPRESSION_LEVELS["medium"]
            )
            
            dpi = level_settings["dpi"]
            quality = level_settings["quality"]
            
            # Use Ghostscript for PDF compression
            gs_command = [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/ebook",
                f"-dColorImageResolution={dpi}",
                f"-dGrayImageResolution={dpi}",
                f"-dMonoImageResolution={dpi}",
                f"-dColorImageDownsampleType=/Bicubic",
                f"-dColorImageDownsampleThreshold=1.0",
                f"-dGrayImageDownsampleType=/Bicubic",
                f"-dGrayImageDownsampleThreshold=1.0",
                f"-dMonoImageDownsampleType=/Bicubic",
                f"-dMonoImageDownsampleThreshold=1.0",
                f"-dJPEGQ={quality}",
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                "-sOutputFile=" + output_path,
                input_path
            ]
            
            process = subprocess.run(
                gs_command, 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            return os.path.exists(output_path)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Ghostscript error: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error compressing PDF: {str(e)}")
            return False
    
    @staticmethod
    def get_compression_stats(original_path, compressed_path):
        """
        Calculate compression statistics.
        
        Args:
            original_path (str): Path to original PDF
            compressed_path (str): Path to compressed PDF
            
        Returns:
            tuple: (original_size_kb, compressed_size_kb, reduction_percent)
        """
        if not os.path.exists(original_path) or not os.path.exists(compressed_path):
            return 0, 0, 0
            
        original_size = os.path.getsize(original_path)
        compressed_size = os.path.getsize(compressed_path)
        
        original_size_kb = original_size / 1024
        compressed_size_kb = compressed_size / 1024
        
        if original_size > 0:
            reduction_percent = ((original_size - compressed_size) / original_size) * 100
        else:
            reduction_percent = 0
            
        return original_size_kb, compressed_size_kb, reduction_percent
    
    @staticmethod
    def determine_best_compression_level(file_size_kb):
        """
        Automatically determine the best compression level based on file size.
        
        Args:
            file_size_kb (float): File size in KB
            
        Returns:
            str: Compression level
        """
        if file_size_kb <= 500:  # Small files
            return "low"
        elif file_size_kb <= 2000:  # Medium files
            return "medium"
        elif file_size_kb <= 5000:  # Large files
            return "high"
        else:  # Very large files
            return "max"
    
    @staticmethod
    def compress_single_pdf(task_dir, pdf_filename, compression_level="medium", auto_level=False):
        """
        Compress a single PDF file.
        
        Args:
            task_dir (str): Task directory path
            pdf_filename (str): PDF filename
            compression_level (str): Compression level
            auto_level (bool): Whether to automatically determine compression level
            
        Returns:
            dict: Compression information
        """
        input_path = os.path.join(task_dir, pdf_filename)
        
        if not os.path.exists(input_path):
            return {
                "success": False,
                "error": f"PDF file not found: {pdf_filename}"
            }
        
        # Create output filename
        file_base, file_ext = os.path.splitext(pdf_filename)
        output_filename = f"{file_base}_compressed{file_ext}"
        output_path = os.path.join(task_dir, output_filename)
        
        # Determine compression level if auto
        if auto_level:
            file_size_kb = os.path.getsize(input_path) / 1024
            compression_level = CompressPdfWorkflow.determine_best_compression_level(file_size_kb)
        
        # Compress PDF
        success = CompressPdfWorkflow.compress_pdf(
            input_path, 
            output_path, 
            compression_level
        )
        
        if not success:
            return {
                "success": False,
                "error": "PDF compression failed"
            }
        
        # Get compression stats
        original_kb, compressed_kb, reduction = CompressPdfWorkflow.get_compression_stats(
            input_path, 
            output_path
        )
        
        # If compressed file is larger, use the original
        if compressed_kb >= original_kb:
            os.replace(input_path, output_path)
            return {
                "success": True,
                "path": output_path,
                "original_size": original_kb,
                "compressed_size": original_kb,
                "reduction": 0,
                "note": "Compression not beneficial - using original file"
            }
        
        return {
            "success": True,
            "path": output_path,
            "original_size": original_kb,
            "compressed_size": compressed_kb,
            "reduction": reduction,
            "level": compression_level
        }