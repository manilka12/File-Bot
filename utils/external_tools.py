"""
External tool utility functions for the Document Scanner application.

This module provides wrapper functions for interacting with external tools via subprocess calls.
"""

import os
import re
import shutil
import subprocess
from typing import List, Dict, Any, Optional, Union, Tuple
import logging
import shlex

from app.exceptions import (
    ExternalToolError, 
    ToolNotFoundError, 
    LibreOfficeError,
    GhostscriptError,
    ScannerError,
    DocumentScannerError,
    PdfProcessingError
)
from utils.logging_utils import setup_logger, with_context
from config.settings import (
    DEFAULT_COMMAND_TIMEOUT,
    LIBREOFFICE_TIMEOUT,
    GHOSTSCRIPT_TIMEOUT,
    SCANNER_TIMEOUT,
    PANDOC_TIMEOUT,
    PDF_TOOLS_TIMEOUT
)

# Set up logger
logger = setup_logger(__name__)

# Error pattern matchers for various external tools
ERROR_PATTERNS = {
    'libreoffice': [
        (r'Error: source file could not be loaded', 'Source file could not be loaded'),
        (r'Error: office process died', 'LibreOffice process died unexpectedly'),
        (r'I/O error: .+', 'I/O error occurred in LibreOffice'),
        (r'unknown error .+', 'Unknown LibreOffice error'),
        (r'Error: Unable to connect to .+', 'Unable to connect to LibreOffice service'),
    ],
    'gs': [
        (r'Error: .*invalidfont.*', 'Invalid font error in document'),
        (r'Error: .*invalidfileaccess.*in.*', 'Permission denied or cannot access file'),
        (r'Error: .*limitcheck.*', 'Memory limit exceeded during processing'),
        (r'Error: .*invalidaccess.*', 'Invalid access error during processing'),
        (r'Error: .*undefined.*in.*', 'Undefined PDF element encountered'),
        (r'Error: .*syntaxerror.*', 'Syntax error in PDF document'),
        (r'Error: .*PDFfile.*', 'Invalid or corrupted PDF file'),
        (r'Error: .*invalidcontext.*', 'Invalid context in PDF file'),
        (r'Error: .*typecheck.*', 'Type check error in PDF processing'),
    ],
    'scanner': [
        (r'Error: no (?:images|pdfs) found', 'No images or PDFs found to process'),
        (r'FileNotFoundError', 'Scanner could not find the required file'),
        (r'Original file not found: .*', 'Original file not found for scanning'),
        (r'Could not open image', 'Could not open image for scanning'),
        (r'Could not find any pages', 'No pages found in the document'),
        (r'Failed to create PDF', 'Failed to create PDF from scanned image'),
    ],
    'pandoc': [
        (r'Error: Could not find data file', 'Could not find required template or data file'),
        (r'Error: .*parse error.*', 'Parse error in Markdown document'),
        (r'Error: .*not found.*', 'Required file not found'),
        (r"Failed to load .+", "Failed to load required file"),
    ],
    'pdftk': [
        (r'Error: Failed to open PDF file', 'Failed to open PDF file'),
        (r'Error: .*Rotate not allowed.*', 'Page rotation not allowed in this context'),
        (r'Error: .*PDF file is damaged.*', 'PDF file is damaged or corrupted'),
        (r'Error: .*Error: Unable to find file.*', 'Unable to find specified PDF file'),
        (r'Error: .*Error: Failed to open output file.*', 'Failed to create output file'),
    ],
    'qpdf': [
        (r'.*syntax error.*', 'Syntax error in PDF document'),
        (r'.*operation failed.*', 'QPDF operation failed'),
        (r'.*no such file.*', 'PDF file not found'),
        (r'.*invalid password.*', 'PDF file requires a password'),
    ],
    'pdfinfo': [
        (r'Syntax Error: Invalid.+', 'Syntax error in PDF document'),
        (r'Error: Cannot open', 'Cannot open PDF file'),
    ]
}


@with_context()
def check_tool_exists(tool_name: str, raise_error: bool = True) -> bool:
    """
    Check if an external tool is available on the system.
    
    Args:
        tool_name: Name of the tool executable
        raise_error: Whether to raise a ToolNotFoundError if the tool is not found
        
    Returns:
        bool: True if the tool exists, False otherwise
        
    Raises:
        ToolNotFoundError: If the tool is not found and raise_error is True
    """
    path = shutil.which(tool_name)
    
    if path is None:
        msg = f"Required tool '{tool_name}' not found in PATH"
        logger.error(msg)
        
        if raise_error:
            raise ToolNotFoundError(tool_name)
        return False
    
    logger.debug(f"Tool '{tool_name}' found at: {path}")
    return True


def _parse_error_output(tool_name: str, stderr: str) -> Optional[str]:
    """
    Parse the error output from a tool to identify common issues.
    
    Args:
        tool_name: Name of the tool
        stderr: Error output from the tool
        
    Returns:
        str: Parsed error message, or None if no pattern matched
    """
    if not stderr or stderr.strip() == '':
        return None
    
    # Get the base name of the tool for pattern matching
    base_tool = tool_name.split('/')[-1]  # Handle absolute paths
    
    # Special case for LibreOffice, which could be called as 'soffice'
    if base_tool == 'soffice':
        base_tool = 'libreoffice'
    
    # Find pattern list for this tool
    patterns = ERROR_PATTERNS.get(base_tool, [])
    
    # Try to match error patterns
    for pattern, message in patterns:
        if re.search(pattern, stderr, re.IGNORECASE):
            return message
    
    # Generic error detection if no specific pattern matched
    error_lines = [line for line in stderr.splitlines() if 'error' in line.lower()]
    if error_lines:
        return error_lines[0].strip()
    
    return None


@with_context()
def run_command(
    cmd: Union[str, List[str]], 
    timeout: Optional[int] = None,
    shell: bool = False,
    check_tool: bool = True,
    capture_output: bool = True,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    tool_category: Optional[str] = None
) -> subprocess.CompletedProcess:
    """
    Run an external command with proper error handling.
    
    Args:
        cmd: Command to run (string or list of strings)
        timeout: Timeout in seconds (default: from settings or 300s)
        shell: Whether to run the command in a shell
        check_tool: Whether to check if the tool exists before running
        capture_output: Whether to capture stdout and stderr
        cwd: Working directory for the command
        env: Environment variables for the command
        tool_category: Category of tool for error handling ('libreoffice', 'gs', etc.)
        
    Returns:
        subprocess.CompletedProcess: Result of the command
        
    Raises:
        ToolNotFoundError: If the tool doesn't exist and check_tool is True
        ExternalToolError: If the command fails or times out
        LibreOfficeError: If a LibreOffice command fails
        GhostscriptError: If a Ghostscript command fails
        ScannerError: If a scanner command fails
    """
    # If timeout not specified, use default from settings
    if timeout is None:
        timeout = DEFAULT_COMMAND_TIMEOUT
    
    # If cmd is a string and we're not using shell, split it into a list
    if isinstance(cmd, str) and not shell:
        cmd_list = shlex.split(cmd)
    else:
        cmd_list = cmd if isinstance(cmd, list) else cmd
    
    # Get the tool name for checking
    tool_name = cmd_list[0] if isinstance(cmd_list, list) else cmd_list.split()[0]
    
    # Infer tool category if not provided
    if not tool_category:
        base_tool = tool_name.split('/')[-1]
        if base_tool in ['soffice', 'libreoffice']:
            tool_category = 'libreoffice'
        elif base_tool == 'gs':
            tool_category = 'gs'
        elif 'scanner' in base_tool or base_tool in ['scan-script', 'scan.py', 'scanner.py']:
            tool_category = 'scanner'
        elif base_tool == 'pandoc':
            tool_category = 'pandoc'
        elif base_tool in ['pdftk', 'qpdf', 'pdfinfo', 'pdftotext']:
            tool_category = base_tool
    
    # Check if the tool exists if requested
    if check_tool:
        check_tool_exists(tool_name)
    
    # Environment setup - merge provided env with current environment
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    else:
        full_env = None
    
    # Log the command
    cmd_str = cmd if isinstance(cmd, str) else " ".join([str(c) for c in cmd_list])
    
    # Add working directory to log if specified
    cwd_info = f" in directory {cwd}" if cwd else ""
    logger.info(f"Running command: {cmd_str}{cwd_info}")
    
    try:
        # Run the command
        result = subprocess.run(
            cmd_list,
            shell=shell,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=full_env
        )
        
        # Check for errors
        if result.returncode != 0:
            error_msg = f"Command failed with return code {result.returncode}"
            
            # Log details
            logger.error(error_msg)
            if result.stdout and len(result.stdout) > 0:
                logger.debug(f"Command stdout: {result.stdout}")
            if result.stderr and len(result.stderr) > 0:
                logger.error(f"Command stderr: {result.stderr}")
            
            # Parse error output for specific messages
            parsed_error = _parse_error_output(tool_name, result.stderr)
            error_details = parsed_error if parsed_error else "Unknown error"
            
            # Raise appropriate exception based on the tool category
            if tool_category == 'libreoffice':
                raise LibreOfficeError(
                    message=f"LibreOffice error: {error_details}",
                    command=cmd_str,
                    stderr=result.stderr,
                    returncode=result.returncode
                )
            elif tool_category == 'gs':
                raise GhostscriptError(
                    message=f"Ghostscript error: {error_details}",
                    command=cmd_str,
                    stderr=result.stderr,
                    returncode=result.returncode
                )
            elif tool_category == 'scanner':
                raise ScannerError(
                    message=f"Scanner error: {error_details}",
                    command=cmd_str,
                    stderr=result.stderr,
                    returncode=result.returncode
                )
            elif tool_category in ['pdftk', 'qpdf', 'pdfinfo', 'pdftotext']:
                raise PdfProcessingError(
                    message=f"PDF processing error: {error_details}",
                    filename=None  # We don't have filename context here
                )
            else:
                raise ExternalToolError(
                    message=f"External command error: {error_details}",
                    command=cmd_str,
                    stderr=result.stderr,
                    returncode=result.returncode
                )
        
        # Log success
        logger.debug(f"Command completed successfully with return code {result.returncode}")
        return result
    
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout} seconds: {cmd_str}")
        
        # For timeout errors, create specific error message based on tool category
        if tool_category == 'libreoffice':
            raise LibreOfficeError(
                message=f"LibreOffice command timed out after {timeout} seconds",
                command=cmd_str,
                stderr=None,
                returncode=None
            )
        elif tool_category == 'gs':
            raise GhostscriptError(
                message=f"Ghostscript command timed out after {timeout} seconds",
                command=cmd_str,
                stderr=None,
                returncode=None
            )
        elif tool_category == 'scanner':
            raise ScannerError(
                message=f"Scanner command timed out after {timeout} seconds",
                command=cmd_str,
                stderr=None,
                returncode=None
            )
        else:
            raise ExternalToolError(
                message=f"Command timed out after {timeout} seconds",
                command=cmd_str
            )
    
    except FileNotFoundError:
        logger.error(f"Command not found: {cmd_str}")
        raise ToolNotFoundError(tool_name)
    
    except Exception as e:
        logger.error(f"Unexpected error running command: {cmd_str} - {str(e)}", exc_info=True)
        
        raise ExternalToolError(
            message=f"Unexpected error: {str(e)}",
            command=cmd_str
        )


@with_context()
def run_libreoffice(
    args: List[str],
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    check_installation: bool = True
) -> subprocess.CompletedProcess:
    """
    Run LibreOffice with the given arguments.
    
    Args:
        args: Arguments to pass to LibreOffice
        timeout: Timeout in seconds (defaults to LIBREOFFICE_TIMEOUT)
        cwd: Working directory
        env: Environment variables
        check_installation: Whether to verify LibreOffice installation
        
    Returns:
        subprocess.CompletedProcess: Result of the command
        
    Raises:
        ToolNotFoundError: If LibreOffice is not found
        LibreOfficeError: If the command fails
    """
    # Use the configured timeout if not specified
    if timeout is None:
        timeout = LIBREOFFICE_TIMEOUT
    
    # Check for soffice (LibreOffice binary) first
    libreoffice_bin = "soffice"
    if check_installation:
        if not shutil.which(libreoffice_bin):
            libreoffice_bin = "libreoffice"
            if not shutil.which(libreoffice_bin):
                raise ToolNotFoundError("libreoffice")
    
    # Prepare environment - set HOME if not provided
    # This can prevent user profile issues
    if env is None:
        env = {}
        
    # Always include user profile directory if not explicitly set
    if "HOME" not in env and "USER_PROFILE" not in env:
        if cwd:
            env["HOME"] = cwd
    
    # Ensure user installation is set up for headless mode
    env["SAL_USE_VCLPLUGIN"] = "gen"
    
    # Build the command
    cmd = [libreoffice_bin] + args
    
    logger.info(f"Running LibreOffice: {' '.join(cmd)}")
    
    try:
        return run_command(
            cmd,
            timeout=timeout,
            check_tool=False,  # Already checked if requested
            capture_output=True,
            cwd=cwd,
            env=env,
            tool_category='libreoffice'
        )
    except ExternalToolError as e:
        # This should not happen as run_command should return LibreOfficeError directly
        # But just in case...
        raise LibreOfficeError(
            message=str(e),
            command=e.command,
            stderr=getattr(e, 'stderr', None),
            returncode=getattr(e, 'returncode', None)
        )


@with_context()
def run_ghostscript(
    args: List[str],
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
) -> subprocess.CompletedProcess:
    """
    Run Ghostscript with the given arguments.
    
    Args:
        args: Arguments to pass to Ghostscript
        timeout: Timeout in seconds (defaults to GHOSTSCRIPT_TIMEOUT)
        cwd: Working directory
        env: Environment variables
        
    Returns:
        subprocess.CompletedProcess: Result of the command
        
    Raises:
        ToolNotFoundError: If Ghostscript is not found
        GhostscriptError: If the command fails
    """
    # Use the configured timeout if not specified
    if timeout is None:
        timeout = GHOSTSCRIPT_TIMEOUT
    
    # Ghostscript binary name
    gs_bin = "gs"
    
    # Always verify that Ghostscript exists
    check_tool_exists(gs_bin)
    
    # Build the command
    cmd = [gs_bin] + args
    
    logger.info(f"Running Ghostscript: {' '.join(cmd)}")
    
    try:
        return run_command(
            cmd,
            timeout=timeout,
            check_tool=False,  # Already checked above
            capture_output=True,
            cwd=cwd,
            env=env,
            tool_category='gs'
        )
    except ExternalToolError as e:
        # This should not happen as run_command should return GhostscriptError directly
        # But just in case...
        raise GhostscriptError(
            message=str(e),
            command=e.command,
            stderr=getattr(e, 'stderr', None),
            returncode=getattr(e, 'returncode', None)
        )


@with_context()
def run_pandoc(
    args: List[str],
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
) -> subprocess.CompletedProcess:
    """
    Run Pandoc with the given arguments.
    
    Args:
        args: Arguments to pass to Pandoc
        timeout: Timeout in seconds (defaults to PANDOC_TIMEOUT)
        cwd: Working directory
        env: Environment variables
        
    Returns:
        subprocess.CompletedProcess: Result of the command
        
    Raises:
        ToolNotFoundError: If Pandoc is not found
        ExternalToolError: If the command fails
    """
    # Use the configured timeout if not specified
    if timeout is None:
        timeout = PANDOC_TIMEOUT
    
    # Pandoc binary name
    pandoc_bin = "pandoc"
    
    # Always verify Pandoc exists
    check_tool_exists(pandoc_bin)
    
    # Build the command
    cmd = [pandoc_bin] + args
    
    logger.info(f"Running Pandoc: {' '.join(cmd)}")
    
    return run_command(
        cmd,
        timeout=timeout,
        check_tool=False,  # Already checked above
        capture_output=True,
        cwd=cwd,
        env=env,
        tool_category='pandoc'
    )


@with_context()
def run_scanner_script(
    script_path: str,
    args: List[str],
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
) -> subprocess.CompletedProcess:
    """
    Run the document scanner script with the given arguments.
    
    Args:
        script_path: Path to the scanner script
        args: Arguments to pass to the script
        timeout: Timeout in seconds (defaults to SCANNER_TIMEOUT)
        cwd: Working directory
        env: Environment variables
        
    Returns:
        subprocess.CompletedProcess: Result of the command
        
    Raises:
        ToolNotFoundError: If the script is not found
        ScannerError: If the script fails
        FileNotFoundError: If the script file doesn't exist
    """
    # Use the configured timeout if not specified
    if timeout is None:
        timeout = SCANNER_TIMEOUT
    
    # Check if the script exists
    if not os.path.isfile(script_path):
        logger.error(f"Scanner script not found: {script_path}")
        raise FileNotFoundError(f"Scanner script not found: {script_path}")
    
    # Check if the script is executable (for non-Windows systems)
    if os.name != 'nt' and not os.access(script_path, os.X_OK):
        logger.warning(f"Scanner script is not executable: {script_path}")
        # Try to make it executable
        try:
            os.chmod(script_path, 0o755)
            logger.info(f"Made scanner script executable: {script_path}")
        except Exception as e:
            logger.error(f"Failed to make scanner script executable: {str(e)}")
    
    # Determine how to run the script
    if script_path.endswith('.py'):
        # Run with Python interpreter
        cmd = ['python', script_path] + args
    else:
        # Run directly (assumes script has shebang or is standalone executable)
        cmd = [script_path] + args
    
    logger.info(f"Running scanner script: {' '.join(cmd)}")
    
    return run_command(
        cmd,
        timeout=timeout,
        check_tool=False,  # Already checked above
        capture_output=True,
        cwd=cwd,
        env=env,
        tool_category='scanner'
    )


@with_context()
def run_pdf_tool(
    tool_name: str,
    args: List[str],
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
) -> subprocess.CompletedProcess:
    """
    Run a PDF processing tool with the given arguments.
    
    Args:
        tool_name: Name of the PDF tool ('pdftk', 'qpdf', 'pdfinfo', etc.)
        args: Arguments to pass to the tool
        timeout: Timeout in seconds (defaults to PDF_TOOLS_TIMEOUT)
        cwd: Working directory
        env: Environment variables
        
    Returns:
        subprocess.CompletedProcess: Result of the command
        
    Raises:
        ToolNotFoundError: If the tool is not found
        ExternalToolError: If the command fails
    """
    # Use the configured timeout if not specified
    if timeout is None:
        timeout = PDF_TOOLS_TIMEOUT
    
    # Check if the tool exists
    check_tool_exists(tool_name)
    
    # Build the command
    cmd = [tool_name] + args
    
    logger.info(f"Running PDF tool {tool_name}: {' '.join(cmd)}")
    
    return run_command(
        cmd,
        timeout=timeout,
        check_tool=False,  # Already checked above
        capture_output=True,
        cwd=cwd,
        env=env,
        tool_category=tool_name
    )


@with_context()
def compress_pdf(
    input_path: str, 
    output_path: str, 
    dpi: int = 150, 
    jpeg_quality: int = 80,
    pdfsettings: str = "/ebook"
) -> Dict[str, Any]:
    """
    Compress a PDF file using Ghostscript.
    
    Args:
        input_path: Path to the input PDF file
        output_path: Path to save the compressed PDF
        dpi: Resolution in DPI (lower means smaller file)
        jpeg_quality: JPEG quality (0-100, lower means smaller file)
        pdfsettings: Ghostscript PDF settings preset (/screen, /ebook, /printer, /prepress)
        
    Returns:
        Dict containing success status and error message if any
        
    Notes:
        This function uses Ghostscript to compress the PDF. The compression
        is done by downsampling images and using JPEG compression.
    """
    logger.info(f"Compressing PDF: {input_path} to {output_path}")
    logger.info(f"Compression settings: DPI={dpi}, JPEG Quality={jpeg_quality}")
    
    try:
        # Check if the input file exists
        if not os.path.exists(input_path):
            return {
                "success": False,
                "error": f"Input file not found: {input_path}"
            }
        
        # Create directory for output file if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Ghostscript parameters for PDF compression
        # These settings balance quality and file size
        gs_params = [
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={pdfsettings}",  # Use the provided PDF settings preset
            f"-dColorImageResolution={dpi}",
            f"-dGrayImageResolution={dpi}",
            f"-dMonoImageResolution={dpi}",
            f"-dJPEGQ={jpeg_quality}",
            "-dColorImageDownsampleType=/Bicubic",
            "-dGrayImageDownsampleType=/Bicubic",
            "-dMonoImageDownsampleType=/Bicubic",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            input_path
        ]
        
        # Run Ghostscript
        result = run_ghostscript(gs_params)
        
        # Check if compression was successful
        if os.path.exists(output_path):
            input_size = os.path.getsize(input_path)
            output_size = os.path.getsize(output_path)
            
            compression_ratio = (1 - (output_size / input_size)) * 100
            logger.info(f"PDF compression successful: {compression_ratio:.1f}% reduction")
            logger.info(f"Original: {input_size} bytes, Compressed: {output_size} bytes")
            
            return {
                "success": True,
                "input_size": input_size,
                "output_size": output_size,
                "compression_ratio": compression_ratio
            }
        else:
            logger.error(f"Compressed file not found: {output_path}")
            return {
                "success": False,
                "error": "Output file not created during compression"
            }
            
    except GhostscriptError as e:
        logger.error(f"Ghostscript error during PDF compression: {str(e)}")
        return {
            "success": False,
            "error": f"Ghostscript error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error compressing PDF: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@with_context()
def convert_office_to_pdf(
    input_path: str,
    output_dir: str,
    doc_type: str = 'generic',
    timeout: Optional[int] = None
) -> Optional[str]:
    """
    Convert Office documents (Word, PowerPoint, Excel) to PDF using LibreOffice.
    
    Args:
        input_path: Path to the input document
        output_dir: Directory where the PDF should be saved
        doc_type: Document type ('word', 'powerpoint', 'excel', or 'generic')
        timeout: Timeout in seconds (default: LIBREOFFICE_TIMEOUT)
        
    Returns:
        Optional[str]: Path to the output PDF file if successful, None otherwise
    """
    logger.info(f"Converting {doc_type.upper()} document to PDF: {input_path}")
    
    # Ensure we're working with absolute paths
    abs_input_path = os.path.abspath(input_path)
    abs_output_dir = os.path.abspath(output_dir)
    
    # Prepare environment variables to force headless mode
    env = os.environ.copy()
    env.update({
        'HOME': output_dir,            # Use task directory as HOME to avoid profile issues
        'DISPLAY': '',                 # Empty DISPLAY to prevent X11 connection attempts
        'SAL_USE_VCLPLUGIN': 'svp',    # Use software virtual pixel plugin (no X11 required)
        'SAL_DISABLE_SYNCHRONIZATION': '1', # Disable synchronization that might need X11
        'PYTHONIOENCODING': 'utf-8',
        'LC_ALL': 'C.UTF-8',
        'LANG': 'C.UTF-8',
        'AVOIDX11': '1',               # Force avoidance of X11
        'QT_QPA_PLATFORM': 'offscreen',
        'QT_QPA_FONTDIR': '/usr/share/fonts',  # Explicitly set font directory
        'XAUTHORITY': '/dev/null',
        'NO_AT_BRIDGE': '1',
        'XDG_RUNTIME_DIR': '/tmp'      # Set runtime directory to avoid user-specific paths
    })
    
    # Specific conversion options based on document type
    if doc_type == 'excel':
        # For Excel, use specific export filter with minimal margins
        convert_args = ['--convert-to', 'pdf:calc_pdf_Export', '--outdir', abs_output_dir, abs_input_path]
    elif doc_type == 'powerpoint':
        # For PowerPoint, use specific filter
        convert_args = ['--convert-to', 'pdf:impress_pdf_Export', '--outdir', abs_output_dir, abs_input_path]
    elif doc_type == 'word':
        # For Word, use specific filter
        convert_args = ['--convert-to', 'pdf:writer_pdf_Export', '--outdir', abs_output_dir, abs_input_path]
    else:
        # Generic conversion for other document types
        convert_args = ['--convert-to', 'pdf', '--outdir', abs_output_dir, abs_input_path]
    
    # Full LibreOffice arguments for headless conversion
    args = [
        '--headless',
        '--norestore',
        '--invisible',
        '--nologo',
        '--nolockcheck',
        '--nodefault',
        '--nofirststartwizard'
    ] + convert_args
    
    try:
        # Run LibreOffice for conversion
        result = run_libreoffice(args, timeout=timeout, cwd=output_dir, env=env)
        
        # Get expected output filename
        input_filename = os.path.basename(abs_input_path)
        output_filename = os.path.splitext(input_filename)[0] + '.pdf'
        output_path = os.path.join(abs_output_dir, output_filename)
        
        # Check if conversion was successful
        if os.path.exists(output_path):
            logger.info(f"Successfully converted {doc_type} to PDF: {output_path}")
            return output_path
        else:
            logger.error(f"PDF file not found after conversion: {output_path}")
            logger.error(f"LibreOffice output: {result.stdout}")
            logger.error(f"LibreOffice error: {result.stderr}")
            
            # Try to handle X11 display issues with xvfb-run if available
            if "Can't open display" in result.stderr and shutil.which('xvfb-run'):
                logger.info("Detected X11 issue, trying with xvfb-run...")
                return _try_convert_with_xvfb(abs_input_path, abs_output_dir, output_filename)
            
            return None
            
    except LibreOfficeError as e:
        logger.error(f"LibreOffice error: {str(e)}")
        
        # Check for display errors
        if hasattr(e, 'stderr') and e.stderr and "Can't open display" in e.stderr:
            logger.info("Detected X11 issue in exception, trying with xvfb-run...")
            return _try_convert_with_xvfb(abs_input_path, abs_output_dir, output_filename)
        
        return None
        
    except Exception as e:
        logger.error(f"Unexpected error during document conversion: {str(e)}", exc_info=True)
        return None


def _try_convert_with_xvfb(input_path: str, output_dir: str, output_filename: str) -> Optional[str]:
    """Helper function to try conversion using xvfb-run as fallback"""
    if not shutil.which('xvfb-run'):
        logger.error("xvfb-run not available for fallback conversion")
        return None
        
    output_path = os.path.join(output_dir, output_filename)
    try:
        cmd = [
            'xvfb-run', '-a',
            'soffice',
            '--headless', 
            '--convert-to', 
            'pdf', 
            '--outdir', 
            output_dir,
            input_path
        ]
        
        logger.info(f"Trying fallback conversion with xvfb-run: {' '.join(cmd)}")
        env = os.environ.copy()
        env.update({
            'HOME': output_dir,
            'SAL_USE_VCLPLUGIN': 'svp'
        })
        
        process = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
        
        if os.path.exists(output_path):
            logger.info(f"xvfb-run fallback succeeded: {output_path}")
            return output_path
        else:
            logger.error(f"xvfb-run fallback failed. Error: {process.stderr}")
            return None
    except Exception as e:
        logger.error(f"Error in xvfb-run fallback: {str(e)}")
        return None