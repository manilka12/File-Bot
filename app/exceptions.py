"""
Custom exceptions for the Document Scanner application.
"""

class DocumentScannerError(Exception):
    """Base exception for all Document Scanner errors."""
    pass


class WorkflowError(DocumentScannerError):
    """Base exception for workflow-related errors."""
    def __init__(self, message: str = "Workflow error occurred", workflow_name: str = None):
        self.workflow_name = workflow_name
        self.message = f"{message}" + (f" in {workflow_name}" if workflow_name else "")
        super().__init__(self.message)


class FileProcessingError(WorkflowError):
    """Exception for errors during file processing."""
    def __init__(self, message: str = "Error processing file", workflow_name: str = None, filename: str = None):
        self.filename = filename
        msg = f"{message}" + (f" ({filename})" if filename else "")
        super().__init__(msg, workflow_name)


class InvalidInputError(WorkflowError):
    """Exception for invalid user input."""
    pass


class MergeOrderError(WorkflowError):
    """Exception for errors related to merge order processing."""
    pass


class PdfProcessingError(FileProcessingError):
    """Exception for errors specific to PDF processing."""
    pass


class ExternalToolError(DocumentScannerError):
    """Base exception for errors in external tool execution."""
    def __init__(self, message: str = "External tool error", command: str = None, stderr: str = None, returncode: int = None):
        self.command = command
        self.stderr = stderr
        self.returncode = returncode
        
        details = []
        if command:
            details.append(f"Command: {command}")
        if returncode is not None:
            details.append(f"Exit code: {returncode}")
        if stderr:
            details.append(f"Error output: {stderr}")
            
        full_message = f"{message}" + (f" - {'. '.join(details)}" if details else "")
        super().__init__(full_message)


class ToolNotFoundError(ExternalToolError):
    """Exception when an external tool is not found."""
    def __init__(self, tool_name: str):
        super().__init__(f"Required tool not found: {tool_name}")


class LibreOfficeError(ExternalToolError):
    """Exception for LibreOffice-specific errors."""
    pass


class GhostscriptError(ExternalToolError):
    """Exception for Ghostscript-specific errors."""
    pass


class ScannerError(ExternalToolError):
    """Exception for Document Scanner-specific errors."""
    pass


class ApiError(DocumentScannerError):
    """Exception for API-related errors."""
    def __init__(self, message: str = "API error occurred", status_code: int = None, endpoint: str = None):
        self.status_code = status_code
        self.endpoint = endpoint
        
        details = []
        if endpoint:
            details.append(f"Endpoint: {endpoint}")
        if status_code:
            details.append(f"Status code: {status_code}")
            
        full_message = f"{message}" + (f" - {'. '.join(details)}" if details else "")
        super().__init__(full_message)


class WhatsAppApiError(ApiError):
    """Exception for WhatsApp API-related errors."""
    pass


class ConfigurationError(DocumentScannerError):
    """Exception for configuration issues."""
    pass


class StateManagementError(DocumentScannerError):
    """Exception for errors related to state management."""
    pass