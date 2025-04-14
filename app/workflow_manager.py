"""
Workflow manager for the Document Scanner application.
"""

import os
import uuid
import base64
import logging
from utils.file_utils import cleanup_task_universal, read_order_file

from workflows.merge_workflow import MergeWorkflow
from workflows.split_workflow import SplitWorkflow
from workflows.scan_workflow import ScanWorkflow
from workflows.word_to_pdf_workflow import WordToPdfWorkflow
from workflows.powerpoint_to_pdf_workflow import PowerPointToPdfWorkflow
from workflows.excel_to_pdf_workflow import ExcelToPdfWorkflow
from workflows.compress_pdf_workflow import CompressPdfWorkflow
from workflows.markdown_to_pdf_workflow import MarkdownToPdfWorkflow

from config.settings import DOWNLOAD_BASE_DIR

logger = logging.getLogger(__name__)

class WorkflowManager:
    """Manages workflows for document processing tasks."""
    
    def __init__(self, whatsapp_client):
        """
        Initialize the workflow manager.
        
        Args:
            whatsapp_client: Instance of WhatsAppClient
        """
        self.whatsapp_client = whatsapp_client
        self.active_workflows = {}
        
    def start_workflow(self, sender_jid, workflow_type):
        """
        Start a new workflow for a user.
        
        Args:
            sender_jid (str): The user's JID
            workflow_type (str): Type of workflow ('merge', 'split', 'scan', 'word_to_pdf', 'powerpoint_to_pdf', 'excel_to_pdf', 'compress', or 'markdown_to_pdf')
            
        Returns:
            tuple: (success, message)
        """
        # Define initial state based on workflow type
        initial_state = {}
        instruction_message = ""
        
        if workflow_type == "merge":
            initial_state = {"merge_order": {}}
            instruction_message = "Started PDF Merge. Send PDFs one by one.\nReply to a PDF with just a number (e.g., '1') to change order.\nSend 'done' when finished."
        elif workflow_type == "split":
            initial_state = {"split_files": {}}
            instruction_message = "Started PDF Split. Send the PDF file to split.\nThen, *reply to that PDF message* with page ranges (e.g., '1-10', '15', '20-25', one per line or comma-separated)."
        elif workflow_type == "scan":
            initial_state = {"scan_order": {}, "images": []}
            instruction_message = "Started Document Scan. Send images one by one.\nReply to an image with a number to change order.\nSend 'done' when finished."
        elif workflow_type == "word_to_pdf":
            initial_state = {}
            instruction_message = "Started Word to PDF conversion. Send your Word documents (.doc or .docx) one by one.\nSend 'done' when you've sent all documents to convert."
        elif workflow_type == "powerpoint_to_pdf":
            initial_state = {}
            instruction_message = "Started PowerPoint to PDF conversion. Send your PowerPoint presentations (.ppt, .pptx, .pps, or .ppsx) one by one.\nSend 'done' when you've sent all presentations to convert."
        elif workflow_type == "excel_to_pdf":
            initial_state = {}
            instruction_message = "Started Excel to PDF conversion. Send your Excel spreadsheets (.xls, .xlsx, .xlsm, .xlsb, or .csv) one by one.\nSend 'done' when you've sent all spreadsheets to convert."
        elif workflow_type == "compress":
            initial_state = {"compress_files": {}}
            instruction_message = "Started PDF Compression. Send your PDF files one by one, and I'll help you compress them to reduce file size while maintaining quality.\nFor each PDF, you can choose compression level: 'low', 'medium', 'high', 'max', or 'auto'.\nSend 'done' when you've sent all PDFs to compress."
        elif workflow_type == "markdown_to_pdf":
            initial_state = {"markdown_content": [], "message_ids": []}
            instruction_message = "Started Markdown to PDF conversion. Send your markdown text messages one by one. All messages will be combined in sequence.\nUse standard markdown formatting (# for headings, ** for bold, etc.).\nSend 'done' when you've finished sending all markdown text."
        else:
            return False, "Invalid workflow type."
        
        # Create task directory
        task_id = str(uuid.uuid4())
        safe_sender_jid = "".join(c if c.isalnum() else "_" for c in sender_jid)
        task_dir = os.path.join(DOWNLOAD_BASE_DIR, safe_sender_jid, task_id)
        
        try:
            os.makedirs(task_dir, exist_ok=True)
            
            # Initialize new workflow
            self.active_workflows[sender_jid] = {
                "task_id": task_id,
                "task_dir": task_dir,
                "workflow_type": workflow_type,
                **initial_state
            }
            
            # Send instructions to user
            self.whatsapp_client.send_text(sender_jid, instruction_message)
            return True, task_dir
            
        except Exception as e:
            logger.error(f"Failed to start {workflow_type} workflow: {str(e)}")
            return False, f"Sorry, failed to start the {workflow_type} process."
    
    def handle_pdf_save(self, sender_jid, message_data):
        """
        Handle saving PDF files for any workflow.
        
        Args:
            sender_jid (str): The user's JID
            message_data (dict): The message data
            
        Returns:
            str: Saved filename if successful, None otherwise
        """
        if sender_jid not in self.active_workflows:
            return None

        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        wf_type = workflow_info["workflow_type"]
        
        # Extract message info
        message_id = message_data.get('key', {}).get('id')
        message_holder = message_data.get('message', {})
        base64_string = message_holder.get('base64')
        doc_message = message_holder.get('documentMessage', {})
        mimetype = doc_message.get('mimetype')
        
        if not all([message_id, base64_string, mimetype == 'application/pdf']):
            return None

        saved_filename = f"{message_id}.pdf"
        file_path = os.path.join(task_dir, saved_filename)
        
        try:
            # Save PDF
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(base64_string))

            if wf_type == "merge":
                return MergeWorkflow.handle_pdf_save(task_dir, message_id, saved_filename)
            
            elif wf_type == "split":
                result, message = SplitWorkflow.handle_pdf_save(task_dir, message_id, saved_filename, workflow_info)
                if message:
                    self.whatsapp_client.send_text(sender_jid, message)
                return result
                
            elif wf_type == "compress":
                result, message = CompressPdfWorkflow.handle_pdf_save(task_dir, message_id, saved_filename, workflow_info)
                if message:
                    self.whatsapp_client.send_text(sender_jid, message)
                return result

            return saved_filename

        except Exception as e:
            logger.error(f"Failed to save PDF: {str(e)}")
            return None
    
    def handle_image_save(self, sender_jid, message_data):
        """
        Handle saving images for scan workflow.
        
        Args:
            sender_jid (str): The user's JID
            message_data (dict): The message data
            
        Returns:
            str: Saved filename if successful, None otherwise
        """
        if sender_jid not in self.active_workflows:
            return None

        workflow_info = self.active_workflows[sender_jid]
        if workflow_info["workflow_type"] != "scan":
            return None

        task_dir = workflow_info["task_dir"]
        
        # Extract message info
        message_id = message_data.get('key', {}).get('id')
        message_holder = message_data.get('message', {})
        base64_string = message_holder.get('base64')
        img_message = message_holder.get('imageMessage', {})
        mimetype = img_message.get('mimetype')
        
        if not all([message_id, base64_string, mimetype and mimetype.startswith('image/')]):
            return None

        saved_filename = f"{message_id}.jpg"
        file_path = os.path.join(task_dir, saved_filename)
        
        try:
            # Save original image
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(base64_string))
            
            logger.info(f"Original image saved to: {file_path}")
            
            # Process image and update workflow
            result, message = ScanWorkflow.handle_image_save(task_dir, message_id, saved_filename, workflow_info)
            if message:
                self.whatsapp_client.send_text(sender_jid, message)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to save/process image: {str(e)}")
            if os.path.exists(file_path):
                logger.info("Original image was saved but processing failed")
                return saved_filename
            return None
    
    def handle_document_save(self, sender_jid, message_data):
        """
        Handle saving document files (Word, PowerPoint, Excel, PDF) for document-based workflows.
        
        Args:
            sender_jid (str): The user's JID
            message_data (dict): The message data
            
        Returns:
            str: Saved filename if successful, None otherwise
        """
        if sender_jid not in self.active_workflows:
            return None

        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        wf_type = workflow_info["workflow_type"]
        
        # Extract message info
        message_id = message_data.get('key', {}).get('id')
        message_holder = message_data.get('message', {})
        base64_string = message_holder.get('base64')
        doc_message = message_holder.get('documentMessage', {})
        mimetype = doc_message.get('mimetype')
        filename = doc_message.get('fileName', '')
        
        if not all([message_id, base64_string, mimetype]):
            return None

        # Save original filename in workflow_info
        if filename:
            if 'original_filenames' not in workflow_info:
                workflow_info['original_filenames'] = {}
            workflow_info['original_filenames'][message_id] = filename
            logger.info(f"Saved original filename: {filename} for message {message_id}")
            
        # For PDF files, use handle_pdf_save instead
        if mimetype == 'application/pdf':
            return self.handle_pdf_save(sender_jid, message_data)
            
        # For Word files in word_to_pdf workflow
        if wf_type == "word_to_pdf" and (mimetype in [
            'application/msword',  # .doc
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'  # .docx
        ] or filename.lower().endswith(('.doc', '.docx'))):
            # Determine file extension based on mimetype or filename
            if mimetype == 'application/msword' or filename.lower().endswith('.doc'):
                ext = '.doc'
            else:
                ext = '.docx'
                
            saved_filename = f"{message_id}{ext}"
            file_path = os.path.join(task_dir, saved_filename)
            
            try:
                # Save Word document
                with open(file_path, 'wb') as f:
                    f.write(base64.b64decode(base64_string))
                
                logger.info(f"Word document saved to: {file_path}")
                
                # Process document and update workflow
                result, message = WordToPdfWorkflow.handle_document_save(task_dir, message_id, saved_filename, workflow_info)
                if message:
                    self.whatsapp_client.send_text(sender_jid, message)
                
                return result
                
            except Exception as e:
                logger.error(f"Failed to save/process Word document: {str(e)}")
                return None
        
        # For PowerPoint files in powerpoint_to_pdf workflow
        if wf_type == "powerpoint_to_pdf" and (mimetype in [
            'application/vnd.ms-powerpoint',  # .ppt
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # .pptx
            'application/vnd.ms-powerpoint.presentation.macroEnabled.12',  # .pptm
            'application/vnd.openxmlformats-officedocument.presentationml.slideshow',  # .ppsx
            'application/vnd.ms-powerpoint.slideshow.macroEnabled.12'  # .ppsm
        ] or filename.lower().endswith(('.ppt', '.pptx', '.pptm', '.pps', '.ppsx', '.ppsm'))):
            # Determine file extension based on mimetype or filename
            if filename.lower().endswith(('.ppt', '.pptx', '.pptm', '.pps', '.ppsx', '.ppsm')):
                ext = os.path.splitext(filename)[1].lower()
            elif mimetype == 'application/vnd.ms-powerpoint':
                ext = '.ppt'
            elif mimetype == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
                ext = '.pptx'
            elif mimetype == 'application/vnd.openxmlformats-officedocument.presentationml.slideshow':
                ext = '.ppsx'
            else:
                ext = '.pptx'  # Default to .pptx for unknown PowerPoint mimetypes
                
            saved_filename = f"{message_id}{ext}"
            file_path = os.path.join(task_dir, saved_filename)
            
            try:
                # Save PowerPoint presentation
                with open(file_path, 'wb') as f:
                    f.write(base64.b64decode(base64_string))
                
                logger.info(f"PowerPoint presentation saved to: {file_path}")
                
                # Process presentation and update workflow
                result, message = PowerPointToPdfWorkflow.handle_presentation_save(task_dir, message_id, saved_filename, workflow_info)
                if message:
                    self.whatsapp_client.send_text(sender_jid, message)
                
                return result
                
            except Exception as e:
                logger.error(f"Failed to save/process PowerPoint presentation: {str(e)}")
                return None
        
        # For Excel files in excel_to_pdf workflow
        if wf_type == "excel_to_pdf" and (mimetype in [
            'application/vnd.ms-excel',  # .xls
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
            'application/vnd.ms-excel.sheet.macroEnabled.12',  # .xlsm
            'application/vnd.ms-excel.sheet.binary.macroEnabled.12',  # .xlsb
            'text/csv'  # .csv
        ] or filename.lower().endswith(('.xls', '.xlsx', '.xlsm', '.xlsb', '.csv'))):
            # Determine file extension based on mimetype or filename
            if filename.lower().endswith(('.xls', '.xlsx', '.xlsm', '.xlsb', '.csv')):
                ext = os.path.splitext(filename)[1].lower()
            elif mimetype == 'application/vnd.ms-excel':
                ext = '.xls'
            elif mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                ext = '.xlsx'
            elif mimetype == 'text/csv':
                ext = '.csv'
            else:
                ext = '.xlsx'  # Default to .xlsx for unknown Excel mimetypes
                
            saved_filename = f"{message_id}{ext}"
            file_path = os.path.join(task_dir, saved_filename)
            
            try:
                # Save Excel spreadsheet
                with open(file_path, 'wb') as f:
                    f.write(base64.b64decode(base64_string))
                
                logger.info(f"Excel spreadsheet saved to: {file_path}")
                
                # Process spreadsheet and update workflow
                result, message = ExcelToPdfWorkflow.handle_spreadsheet_save(task_dir, message_id, saved_filename, workflow_info)
                if message:
                    self.whatsapp_client.send_text(sender_jid, message)
                
                return result
                
            except Exception as e:
                logger.error(f"Failed to save/process Excel spreadsheet: {str(e)}")
                return None
                
        return None
    
    def handle_order_override(self, sender_jid, quoted_stanza_id, new_order_str):
        """
        Handle order override for merge and scan workflows.
        
        Args:
            sender_jid (str): The user's JID
            quoted_stanza_id (str): ID of the quoted message
            new_order_str (str): New order as string
        """
        if sender_jid not in self.active_workflows:
            return
            
        workflow_info = self.active_workflows[sender_jid]
        wf_type = workflow_info.get("workflow_type")
        if wf_type not in ["merge", "scan"]:
            return
            
        task_dir = workflow_info["task_dir"]
        
        # Determine file extension based on workflow type
        extension = ".pdf" if wf_type == "merge" else ".jpg"
        target_filename = f"{quoted_stanza_id}{extension}"
        
        if wf_type == "merge":
            success, message = MergeWorkflow.handle_order_override(task_dir, target_filename, new_order_str)
        else:  # scan
            success, message = ScanWorkflow.handle_order_override(task_dir, target_filename, new_order_str)
        
        self.whatsapp_client.send_text(sender_jid, message)
    
    def handle_merge_workflow(self, sender_jid, message_text, quoted_stanza_id):
        """
        Handle merge workflow commands.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
            quoted_stanza_id (str): ID of the quoted message
        """
        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        
        if message_text.lower() == 'done':
            order_data = read_order_file(task_dir)
            if not order_data:
                self.whatsapp_client.send_text(sender_jid, "No PDFs received for merge.")
                del self.active_workflows[sender_jid]
                return
                
            merged_pdf_path, missing_files = MergeWorkflow.merge_pdfs_in_order(task_dir, order_data)
            sent_message_id = None
            final_output_files = []

            if merged_pdf_path:
                _, sent_message_id = self.whatsapp_client.send_media(
                    sender_jid, 
                    merged_pdf_path, 
                    "Here is your merged PDF."
                )
                if sent_message_id:
                    final_output_files.append({
                        "path": merged_pdf_path,
                        "sent_id": sent_message_id
                    })

            should_cleanup = (merged_pdf_path is None) or (sent_message_id is not None)
            if should_cleanup:
                cleanup_task_universal(
                    task_dir,
                    list(order_data.keys()),
                    final_output_files
                )
                del self.active_workflows[sender_jid]

        elif quoted_stanza_id and message_text.isdigit():
            self.handle_order_override(sender_jid, quoted_stanza_id, message_text)
    
    def handle_split_workflow(self, sender_jid, message_text, quoted_stanza_id):
        """
        Handle split workflow commands.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
            quoted_stanza_id (str): ID of the quoted message
        """
        if not quoted_stanza_id or not message_text:
            return

        workflow_info = self.active_workflows[sender_jid]
        split_files = workflow_info.get("split_files", {})
        task_dir = workflow_info["task_dir"]

        if quoted_stanza_id in split_files:
            source_filename = split_files[quoted_stanza_id]
            source_path = os.path.join(task_dir, source_filename)

            try:
                from pypdf import PdfReader
                reader = PdfReader(source_path)
                total_pages = len(reader.pages)
                
                # Parse the ranges first
                ranges, error = SplitWorkflow.parse_page_ranges(message_text, total_pages)
                if error:
                    self.whatsapp_client.send_text(sender_jid, f"Invalid page range: {error}")
                    return

                if not ranges:
                    self.whatsapp_client.send_text(sender_jid, "Please specify valid page ranges")
                    return

                # Generate split definitions
                split_definitions = SplitWorkflow.generate_split_definitions(ranges, total_pages)
                split_parts = SplitWorkflow.perform_split(task_dir, source_filename, split_definitions)
                
                # Handle the output files
                output_files = []
                sent_count = 0

                for part in split_parts:
                    _, sent_id = self.whatsapp_client.send_media(
                        sender_jid,
                        part["path"],
                        f"Pages {part['range']}"
                    )
                    if sent_id:
                        sent_count += 1
                        output_files.append({
                            "path": part["path"],
                            "sent_id": sent_id
                        })

                # Cleanup after successful processing
                cleanup_task_universal(task_dir, [source_filename], output_files)
                if sent_count > 0:
                    self.whatsapp_client.send_text(sender_jid, f"Split complete: {sent_count} parts sent")

            except Exception as e:
                self.whatsapp_client.send_text(sender_jid, "Failed to process PDF split request")
                logger.error(f"Split failed: {str(e)}")

            finally:
                del self.active_workflows[sender_jid]
    
    def handle_scan_workflow(self, sender_jid, message_text, quoted_stanza_id):
        """
        Handle scan workflow commands.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
            quoted_stanza_id (str): ID of the quoted message
        """
        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        
        if message_text.lower() == 'done':
            order_data = read_order_file(task_dir)
            if not order_data:
                self.whatsapp_client.send_text(sender_jid, "No images received for scanning.")
                del self.active_workflows[sender_jid]
                return
            
            self.whatsapp_client.send_text(sender_jid, "Processing images... This may take a moment.")
            
            # Create PDFs from images
            output_paths = ScanWorkflow.create_pdfs_from_images(task_dir, order_data)
            
            if not output_paths:
                self.whatsapp_client.send_text(sender_jid, "Failed to create PDFs from images.")
                del self.active_workflows[sender_jid]
                return
            
            # Send PDFs to user
            output_files = []
            for output_path in output_paths:
                _, sent_id = self.whatsapp_client.send_media(
                    sender_jid,
                    output_path,
                    f"Scanned document - {os.path.basename(output_path)}"
                )
                if sent_id:
                    output_files.append({
                        "path": output_path,
                        "sent_id": sent_id
                    })
            
            # Cleanup
            if output_files:
                cleanup_task_universal(
                    task_dir,
                    list(order_data.keys()),
                    output_files
                )
                self.whatsapp_client.send_text(sender_jid, "Scan workflow completed. All versions sent.")
            
            del self.active_workflows[sender_jid]
            
        elif quoted_stanza_id and message_text.isdigit():
            self.handle_order_override(sender_jid, quoted_stanza_id, message_text)

    def handle_word_to_pdf_workflow(self, sender_jid, message_text):
        """
        Handle word to PDF workflow commands.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
        """
        if message_text.lower() != 'done':
            return
            
        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        
        # Finalize task and get output files
        self.whatsapp_client.send_text(sender_jid, "Processing Word documents... This may take a moment.")
        output_paths = WordToPdfWorkflow.finalize_task(task_dir, workflow_info)
        
        if not output_paths:
            self.whatsapp_client.send_text(sender_jid, "No Word documents were converted to PDF.")
            del self.active_workflows[sender_jid]
            return
        
        # Send PDFs to user
        output_files = []
        for output_path in output_paths:
            # Get a friendly name for the PDF
            filename = os.path.basename(output_path)
            if filename == "Merged_Documents.pdf":
                message = "Here are all your documents merged into one PDF."
            else:
                message = f"Here is your converted document: {filename}"
                
            _, sent_id = self.whatsapp_client.send_media(
                sender_jid,
                output_path,
                message
            )
            if sent_id:
                output_files.append({
                    "path": output_path,
                    "sent_id": sent_id
                })
        
        # Determine which files to clean up
        input_files = []
        if 'document_versions' in workflow_info:
            for versions in workflow_info['document_versions'].values():
                if 'original' in versions:
                    input_files.append(versions['original'])
        
        # Cleanup
        if output_files:
            cleanup_task_universal(
                task_dir,
                input_files,
                output_files
            )
            self.whatsapp_client.send_text(sender_jid, "Word to PDF conversion completed.")
        
        del self.active_workflows[sender_jid]

    def handle_powerpoint_to_pdf_workflow(self, sender_jid, message_text):
        """
        Handle PowerPoint to PDF workflow commands.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
        """
        if message_text.lower() != 'done':
            return
            
        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        
        # Finalize task and get output files
        self.whatsapp_client.send_text(sender_jid, "Processing PowerPoint presentations... This may take a moment.")
        output_paths = PowerPointToPdfWorkflow.finalize_task(task_dir, workflow_info)
        
        if not output_paths:
            self.whatsapp_client.send_text(sender_jid, "No PowerPoint presentations were converted to PDF.")
            del self.active_workflows[sender_jid]
            return
        
        # Send PDFs to user
        output_files = []
        for output_path in output_paths:
            # Get a friendly name for the PDF
            filename = os.path.basename(output_path)
            if filename == "Merged_Presentations.pdf":
                message = "Here are all your presentations merged into one PDF."
            else:
                message = f"Here is your converted presentation: {filename}"
                
            _, sent_id = self.whatsapp_client.send_media(
                sender_jid,
                output_path,
                message
            )
            if sent_id:
                output_files.append({
                    "path": output_path,
                    "sent_id": sent_id
                })
        
        # Determine which files to clean up
        input_files = []
        if 'presentation_versions' in workflow_info:
            for versions in workflow_info['presentation_versions'].values():
                if 'original' in versions:
                    input_files.append(versions['original'])
        
        # Cleanup
        if output_files:
            cleanup_task_universal(
                task_dir,
                input_files,
                output_files
            )
            self.whatsapp_client.send_text(sender_jid, "PowerPoint to PDF conversion completed.")
        
        del self.active_workflows[sender_jid]

    def handle_excel_to_pdf_workflow(self, sender_jid, message_text):
        """
        Handle Excel to PDF workflow commands.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
        """
        if message_text.lower() != 'done':
            return
            
        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        
        # Finalize task and get output files
        self.whatsapp_client.send_text(sender_jid, "Processing Excel spreadsheets... This may take a moment.")
        output_paths = ExcelToPdfWorkflow.finalize_task(task_dir, workflow_info)
        
        if not output_paths:
            self.whatsapp_client.send_text(sender_jid, "No Excel spreadsheets were converted to PDF.")
            del self.active_workflows[sender_jid]
            return
        
        # Send PDFs to user
        output_files = []
        for output_path in output_paths:
            # Get a friendly name for the PDF
            filename = os.path.basename(output_path)
            if filename == "Merged_Spreadsheets.pdf":
                message = "Here are all your spreadsheets merged into one PDF."
            else:
                message = f"Here is your converted spreadsheet: {filename}"
                
            _, sent_id = self.whatsapp_client.send_media(
                sender_jid,
                output_path,
                message
            )
            if sent_id:
                output_files.append({
                    "path": output_path,
                    "sent_id": sent_id
                })
        
        # Determine which files to clean up
        input_files = []
        if 'spreadsheet_versions' in workflow_info:
            for versions in workflow_info['spreadsheet_versions'].values():
                if 'original' in versions:
                    input_files.append(versions['original'])
        
        # Cleanup
        if output_files:
            cleanup_task_universal(
                task_dir,
                input_files,
                output_files
            )
            self.whatsapp_client.send_text(sender_jid, "Excel to PDF conversion completed.")
        
        del self.active_workflows[sender_jid]

    def handle_compress_pdf_workflow(self, sender_jid, message_text):
        """
        Handle PDF compression workflow commands.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
        """
        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        
        # Handle compression level selection for specific PDF
        compress_files = workflow_info.get("compress_files", {})
        if not compress_files:
            if message_text.lower() == 'done':
                self.whatsapp_client.send_text(sender_jid, "No PDFs received for compression.")
                del self.active_workflows[sender_jid]
            return
            
        # If user sent "done", process all PDFs that haven't been processed yet
        if message_text.lower() == 'done':
            self.whatsapp_client.send_text(sender_jid, "Processing PDFs for compression... This may take a moment.")
            
            output_files = []
            for message_id, pdf_filename in compress_files.items():
                # Check if this PDF has already been compressed
                if "compressed_versions" in workflow_info and message_id in workflow_info["compressed_versions"]:
                    continue
                    
                # Use medium compression by default
                result = CompressPdfWorkflow.compress_single_pdf(task_dir, pdf_filename, "medium")
                
                if result["success"]:
                    # Store the compressed version info
                    if "compressed_versions" not in workflow_info:
                        workflow_info["compressed_versions"] = {}
                        
                    workflow_info["compressed_versions"][message_id] = {
                        "original": pdf_filename,
                        "compressed": os.path.basename(result["path"]),
                        "stats": {
                            "original_size": result["original_size"],
                            "compressed_size": result["compressed_size"],
                            "reduction": result["reduction"]
                        }
                    }
                    
                    # Send the compressed PDF to the user
                    result_caption = f"Compressed PDF: {result['reduction']:.1f}% reduction ({result['original_size']:.1f} KB → {result['compressed_size']:.1f} KB)"
                    
                    _, sent_id = self.whatsapp_client.send_media(
                        sender_jid,
                        result["path"],
                        result_caption
                    )
                    
                    if sent_id:
                        output_files.append({
                            "path": result["path"],
                            "sent_id": sent_id
                        })
            
            # Get all input files for cleanup
            input_files = []
            if "compressed_versions" in workflow_info:
                for versions in workflow_info["compressed_versions"].values():
                    input_files.append(versions["original"])
            
            # Cleanup
            if output_files:
                cleanup_task_universal(
                    task_dir,
                    input_files,
                    output_files
                )
                self.whatsapp_client.send_text(sender_jid, "PDF compression completed.")
            else:
                self.whatsapp_client.send_text(sender_jid, "No PDFs were compressed.")
                
            del self.active_workflows[sender_jid]
            return
            
        # Handle compression level selection for the most recently received PDF
        last_received_message_id = next(reversed(compress_files))
        pdf_filename = compress_files[last_received_message_id]
        
        # Check if a valid compression level was specified
        compression_level = message_text.lower()
        is_auto = compression_level == "auto"
        
        if is_auto or compression_level in CompressPdfWorkflow.COMPRESSION_LEVELS:
            # Mark this message as being processed
            self.whatsapp_client.send_text(
                sender_jid, 
                f"Compressing PDF with {'automatic' if is_auto else compression_level} compression level..."
            )
            
            # Process the PDF with the specified compression level
            result = CompressPdfWorkflow.compress_single_pdf(
                task_dir, 
                pdf_filename, 
                compression_level if not is_auto else "medium", 
                auto_level=is_auto
            )
            
            if result["success"]:
                # Store the compressed version info
                if "compressed_versions" not in workflow_info:
                    workflow_info["compressed_versions"] = {}
                    
                workflow_info["compressed_versions"][last_received_message_id] = {
                    "original": pdf_filename,
                    "compressed": os.path.basename(result["path"]),
                    "stats": {
                        "original_size": result["original_size"],
                        "compressed_size": result["compressed_size"],
                        "reduction": result["reduction"],
                        "level": result.get("level", compression_level)
                    }
                }
                
                # Prepare the result message
                if result["reduction"] > 0:
                    result_caption = (
                        f"Compressed PDF ({result.get('level', compression_level)} level): "
                        f"{result['reduction']:.1f}% reduction "
                        f"({result['original_size']:.1f} KB → {result['compressed_size']:.1f} KB)"
                    )
                else:
                    result_caption = (
                        f"Compression not beneficial for this PDF. "
                        f"Original file returned ({result['original_size']:.1f} KB)."
                    )
                
                # Send the compressed PDF
                _, sent_id = self.whatsapp_client.send_media(
                    sender_jid,
                    result["path"],
                    result_caption
                )
                
                if sent_id:
                    # Remove the processed PDF from the list of files to compress
                    del compress_files[last_received_message_id]
                    
                    # Check if there are more PDFs to compress
                    if compress_files:
                        next_pdf_id = next(reversed(compress_files))
                        pdf_size = workflow_info.get("original_sizes", {}).get(next_pdf_id, 0)
                        
                        self.whatsapp_client.send_text(
                            sender_jid,
                            f"Send 'low', 'medium', 'high', 'max', or 'auto' to compress the next PDF ({pdf_size:.1f} KB), or 'done' to finish."
                        )
                    else:
                        self.whatsapp_client.send_text(
                            sender_jid,
                            "All PDFs have been compressed. Send more PDFs to compress or 'done' to finish."
                        )
            else:
                # Compression failed
                self.whatsapp_client.send_text(
                    sender_jid,
                    f"Failed to compress PDF: {result.get('error', 'Unknown error')}"
                )
        else:
            # Invalid compression level
            levels_str = ", ".join(f"'{level}'" for level in CompressPdfWorkflow.COMPRESSION_LEVELS.keys())
            self.whatsapp_client.send_text(
                sender_jid,
                f"Invalid compression level. Please send {levels_str}, or 'auto' for automatic level selection."
            )

    def handle_markdown_to_pdf_workflow(self, sender_jid, message_text, message_id=None):
        """
        Handle markdown to PDF workflow commands and text messages.
        
        Args:
            sender_jid (str): The user's JID
            message_text (str): The message text
            message_id (str): The message ID
        """
        workflow_info = self.active_workflows[sender_jid]
        task_dir = workflow_info["task_dir"]
        
        # If user sent 'done', generate PDF from collected markdown content
        if message_text.lower() == 'done':
            # Check if we have any markdown content
            if not workflow_info.get("markdown_content"):
                self.whatsapp_client.send_text(sender_jid, "No markdown content received.")
                del self.active_workflows[sender_jid]
                return
                
            self.whatsapp_client.send_text(sender_jid, "Converting markdown to PDF... This may take a moment.")
            
            # Generate PDF from markdown content
            result = MarkdownToPdfWorkflow.generate_pdf_from_messages(task_dir, workflow_info)
            
            if not result["success"]:
                self.whatsapp_client.send_text(
                    sender_jid, 
                    f"Failed to convert markdown to PDF: {result.get('error', 'Unknown error')}"
                )
                del self.active_workflows[sender_jid]
                return
                
            # Send the PDF to the user
            _, sent_id = self.whatsapp_client.send_media(
                sender_jid,
                result["path"],
                "Here is your PDF generated from markdown text."
            )
            
            # Cleanup
            if sent_id:
                # Create output files list for cleanup
                output_files = [{
                    "path": result["path"],
                    "sent_id": sent_id
                }]
                
                # No input files to clean as they're just part of workflow_info
                cleanup_task_universal(
                    task_dir,
                    [], # No physical input files to clean
                    output_files
                )
                
                self.whatsapp_client.send_text(sender_jid, "Markdown to PDF conversion completed.")
                
            del self.active_workflows[sender_jid]
            return
                
        # If not 'done', treat the message as markdown content to append
        if message_id:
            success, message = MarkdownToPdfWorkflow.append_markdown_content(
                task_dir,
                message_id,
                message_text,
                workflow_info
            )
            
            if success and message:
                self.whatsapp_client.send_text(sender_jid, message)

    def handle_message(self, message_data):
        """
        Main handler for incoming messages.
        
        Args:
            message_data (dict): The message data
        """
        try:
            if 'data' not in message_data:
                return
                
            message_data = message_data['data']
            if message_data.get('key', {}).get('fromMe', False):
                return

            sender_jid = message_data.get('key', {}).get('remoteJid')
            message_id = message_data.get('key', {}).get('id')
            message_type = message_data.get('messageType')
            message_holder = message_data.get('message', {})
            
            # Extract context info (for quoted messages)
            context_info = message_data.get('contextInfo')
            if context_info is None and 'messageContextInfo' in message_holder:
                context_info = message_holder['messageContextInfo']
                
            quoted_stanza_id = context_info.get('stanzaId') if context_info and 'quotedMessage' in context_info else None

            # Extract message text
            message_text = None
            if message_type == 'conversation':
                message_text = message_holder.get('conversation', '').strip()
            elif message_type == 'extendedTextMessage':
                message_text = message_holder.get('extendedTextMessage', {}).get('text', '').strip()

            # Check if user is in an active workflow
            is_in_workflow = sender_jid in self.active_workflows
            
            # Handle workflow start commands
            if message_text and not is_in_workflow:
                command = message_text.lower()
                
                if command == 'merge pdf':
                    self.start_workflow(sender_jid, "merge")
                    return
                    
                elif command == 'split pdf':
                    self.start_workflow(sender_jid, "split")
                    return
                    
                elif command == 'scan document':
                    self.start_workflow(sender_jid, "scan")
                    return

                elif command == 'word to pdf':
                    self.start_workflow(sender_jid, "word_to_pdf")
                    return

                elif command == 'powerpoint to pdf':
                    self.start_workflow(sender_jid, "powerpoint_to_pdf")
                    return

                elif command == 'excel to pdf':
                    self.start_workflow(sender_jid, "excel_to_pdf")
                    return

                elif command == 'compress pdf':
                    self.start_workflow(sender_jid, "compress")
                    return

                elif command == 'markdown to pdf':
                    self.start_workflow(sender_jid, "markdown_to_pdf")
                    return
            
            # Handle active workflow interactions
            if is_in_workflow:
                workflow_info = self.active_workflows[sender_jid]
                wf_type = workflow_info["workflow_type"]

                # Handle PDF documents
                if message_type == 'documentMessage' and message_holder.get('documentMessage', {}).get('mimetype') == 'application/pdf' and 'base64' in message_holder:
                    self.handle_pdf_save(sender_jid, message_data)
                    return

                # Handle image messages for scan workflow
                if message_type == 'imageMessage' and message_holder.get('imageMessage', {}).get('mimetype', '').startswith('image/') and 'base64' in message_holder:
                    self.handle_image_save(sender_jid, message_data)
                    return

                # Handle document messages for word_to_pdf workflow
                if message_type == 'documentMessage' and 'base64' in message_holder:
                    self.handle_document_save(sender_jid, message_data)
                    return

                # Handle text commands based on workflow type
                if wf_type == "merge":
                    self.handle_merge_workflow(sender_jid, message_text, quoted_stanza_id)
                    return
                    
                elif wf_type == "split":
                    self.handle_split_workflow(sender_jid, message_text, quoted_stanza_id)
                    return
                    
                elif wf_type == "scan":
                    self.handle_scan_workflow(sender_jid, message_text, quoted_stanza_id)
                    return

                elif wf_type == "word_to_pdf":
                    self.handle_word_to_pdf_workflow(sender_jid, message_text)
                    return

                elif wf_type == "powerpoint_to_pdf":
                    self.handle_powerpoint_to_pdf_workflow(sender_jid, message_text)
                    return

                elif wf_type == "excel_to_pdf":
                    self.handle_excel_to_pdf_workflow(sender_jid, message_text)
                    return

                elif wf_type == "compress":
                    self.handle_compress_pdf_workflow(sender_jid, message_text)
                    return

                elif wf_type == "markdown_to_pdf":
                    self.handle_markdown_to_pdf_workflow(sender_jid, message_text, message_id)
                    return

        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            if 'sender_jid' in locals() and sender_jid:
                try:
                    self.whatsapp_client.send_text(sender_jid, "An internal error occurred processing your request.")
                except Exception:
                    pass
