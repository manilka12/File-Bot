"""
Unit tests for split_workflow.py
"""

import os
import pytest
import tempfile
from unittest import mock

from workflows.split_workflow import SplitWorkflow

class TestSplitWorkflow:
    """Test cases for SplitWorkflow class"""
    
    def test_parse_page_ranges_valid_input(self):
        """Test parse_page_ranges with valid inputs"""
        # Test single page
        ranges, error = SplitWorkflow.parse_page_ranges("5", 10)
        assert error is None
        assert ranges == [(5, 5)]
        
        # Test multiple single pages
        ranges, error = SplitWorkflow.parse_page_ranges("1, 3, 5", 10)
        assert error is None
        assert ranges == [(1, 1), (3, 3), (5, 5)]
        
        # Test range
        ranges, error = SplitWorkflow.parse_page_ranges("1-5", 10)
        assert error is None
        assert ranges == [(1, 5)]
        
        # Test multiple ranges
        ranges, error = SplitWorkflow.parse_page_ranges("1-3, 5-7", 10)
        assert error is None
        assert ranges == [(1, 3), (5, 7)]
        
        # Test mixed single pages and ranges
        ranges, error = SplitWorkflow.parse_page_ranges("1, 3-5, 8", 10)
        assert error is None
        assert ranges == [(1, 1), (3, 5), (8, 8)]
        
        # Test with spaces and newlines
        ranges, error = SplitWorkflow.parse_page_ranges("1\n3-5 8", 10)
        assert error is None
        assert ranges == [(1, 1), (3, 5), (8, 8)]
        
        # Test with adjacent ranges (should merge)
        ranges, error = SplitWorkflow.parse_page_ranges("1-3, 4-6", 10)
        assert error is None
        assert ranges == [(1, 6)]  # Merged
        
        # Test with overlapping ranges (should merge)
        ranges, error = SplitWorkflow.parse_page_ranges("1-5, 3-7", 10)
        assert error is None
        assert ranges == [(1, 7)]  # Merged
        
        # Test empty input
        ranges, error = SplitWorkflow.parse_page_ranges("", 10)
        assert error is None
        assert ranges == []
        
    def test_parse_page_ranges_invalid_input(self):
        """Test parse_page_ranges with invalid inputs"""
        # Test out of bounds (too high)
        ranges, error = SplitWorkflow.parse_page_ranges("11", 10)
        assert ranges is None
        assert "Invalid page number" in error
        
        # Test out of bounds (too low)
        ranges, error = SplitWorkflow.parse_page_ranges("0", 10)
        assert ranges is None
        assert "Invalid page number" in error
        
        # Test invalid range format
        ranges, error = SplitWorkflow.parse_page_ranges("5-3", 10)
        assert ranges is None
        assert "Invalid range" in error
        
        # Test non-numeric input
        ranges, error = SplitWorkflow.parse_page_ranges("abc", 10)
        assert ranges is None
        assert "Invalid page format" in error
        
        # Test mixed valid and invalid
        ranges, error = SplitWorkflow.parse_page_ranges("1, abc, 5", 10)
        assert ranges is None
        assert "Invalid page format" in error
        
    def test_generate_split_definitions(self):
        """Test generate_split_definitions"""
        # Test with single range in middle
        ranges = [(3, 5)]
        splits = SplitWorkflow.generate_split_definitions(ranges, 10)
        assert splits == [
            {"start": 1, "end": 2, "requested": False},
            {"start": 3, "end": 5, "requested": True},
            {"start": 6, "end": 10, "requested": False}
        ]
        
        # Test with range at start
        ranges = [(1, 3)]
        splits = SplitWorkflow.generate_split_definitions(ranges, 10)
        assert splits == [
            {"start": 1, "end": 3, "requested": True},
            {"start": 4, "end": 10, "requested": False}
        ]
        
        # Test with range at end
        ranges = [(8, 10)]
        splits = SplitWorkflow.generate_split_definitions(ranges, 10)
        assert splits == [
            {"start": 1, "end": 7, "requested": False},
            {"start": 8, "end": 10, "requested": True}
        ]
        
        # Test with multiple ranges
        ranges = [(1, 3), (5, 7), (9, 10)]
        splits = SplitWorkflow.generate_split_definitions(ranges, 10)
        assert splits == [
            {"start": 1, "end": 3, "requested": True},
            {"start": 4, "end": 4, "requested": False},
            {"start": 5, "end": 7, "requested": True},
            {"start": 8, "end": 8, "requested": False},
            {"start": 9, "end": 10, "requested": True}
        ]
        
        # Test with empty ranges
        ranges = []
        splits = SplitWorkflow.generate_split_definitions(ranges, 10)
        assert splits == []
    
    @mock.patch('workflows.split_workflow.PdfReader')
    @mock.patch('workflows.split_workflow.PdfWriter')
    @mock.patch('builtins.open')
    def test_perform_split(self, mock_open, mock_writer_class, mock_reader_class):
        """Test perform_split functionality"""
        # Setup mocks
        mock_reader = mock.MagicMock()
        mock_reader.pages = [mock.MagicMock() for _ in range(10)]  # 10 mock pages
        mock_reader_class.return_value = mock_reader
        
        mock_writer = mock.MagicMock()
        mock_writer_class.return_value = mock_writer
        
        # Test data
        task_dir = "/fake/task/dir"
        source_pdf = "test.pdf"
        split_definitions = [
            {"start": 1, "end": 3, "requested": True},
            {"start": 5, "end": 7, "requested": True}
        ]
        
        # Run the function
        output_files = SplitWorkflow.perform_split(task_dir, source_pdf, split_definitions)
        
        # Assertions
        assert len(output_files) == 2
        assert output_files[0]["range"] == "1-3"
        assert output_files[1]["range"] == "5-7"
        assert mock_writer.add_page.call_count == 6  # 3 pages for first split + 3 for second
        assert mock_writer.write.call_count == 2  # Called for each output file
    
    def test_handle_pdf_save_first_pdf(self):
        """Test handling first PDF save"""
        task_dir = "/fake/task/dir"
        message_id = "msg123"
        saved_filename = "test.pdf"
        workflow_info = {}
        
        filename, message = SplitWorkflow.handle_pdf_save(
            task_dir, message_id, saved_filename, workflow_info
        )
        
        assert filename == saved_filename
        assert "Reply to it with page ranges" in message
        assert workflow_info["split_files"] == {"msg123": "test.pdf"}
    
    def test_handle_pdf_save_duplicate(self):
        """Test handling duplicate PDF save"""
        task_dir = "/fake/task/dir"
        message_id = "msg123"
        saved_filename = "test2.pdf"
        workflow_info = {"split_files": {"msg456": "test1.pdf"}}
        
        filename, message = SplitWorkflow.handle_pdf_save(
            task_dir, message_id, saved_filename, workflow_info
        )
        
        assert filename is None
        assert "PDF already received" in message