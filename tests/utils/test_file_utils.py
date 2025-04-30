"""
Unit tests for file_utils.py
"""

import os
import json
import pytest
import tempfile
import shutil
from unittest import mock

from utils.file_utils import (
    read_order_file,
    write_order_file,
    cleanup_task_universal,
    get_file_extension_from_mimetype
)

class TestFileUtils:
    """Test cases for file utility functions"""
    
    def setup_method(self):
        """Set up test environment before each test"""
        self.temp_dir = tempfile.mkdtemp()
        
    def teardown_method(self):
        """Clean up test environment after each test"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_read_order_file_exists(self):
        """Test reading an existing merge_order.json file"""
        # Create a test file
        order_data = {"files": ["file1.pdf", "file2.pdf"], "order": [0, 1]}
        order_file = os.path.join(self.temp_dir, "merge_order.json")
        with open(order_file, 'w') as f:
            json.dump(order_data, f)
        
        # Test reading
        result = read_order_file(self.temp_dir)
        assert result == order_data
    
    def test_read_order_file_not_exists(self):
        """Test reading when merge_order.json file doesn't exist"""
        result = read_order_file(self.temp_dir)
        assert result == {}
    
    @mock.patch("utils.file_utils.open", side_effect=IOError("Mock IO error"))
    def test_read_order_file_exception(self, mock_open):
        """Test reading with an exception"""
        # Create a dummy file to pass the exists check
        order_file = os.path.join(self.temp_dir, "merge_order.json")
        with open(order_file, 'w') as f:
            f.write('{}')
            
        result = read_order_file(self.temp_dir)
        assert result == {}
    
    def test_write_order_file_success(self):
        """Test successful write to merge_order.json"""
        order_data = {"files": ["file1.pdf", "file2.pdf"], "order": [0, 1]}
        result = write_order_file(self.temp_dir, order_data)
        
        assert result is True
        order_file = os.path.join(self.temp_dir, "merge_order.json")
        assert os.path.exists(order_file)
        
        # Verify content
        with open(order_file, 'r') as f:
            saved_data = json.load(f)
            assert saved_data == order_data
    
    @mock.patch("utils.file_utils.open", side_effect=IOError("Mock IO error"))
    def test_write_order_file_exception(self, mock_open):
        """Test write with an exception"""
        order_data = {"files": ["file1.pdf", "file2.pdf"], "order": [0, 1]}
        result = write_order_file(self.temp_dir, order_data)
        assert result is False
    
    def test_cleanup_task_universal(self):
        """Test cleanup_task_universal function"""
        # Create a test directory structure
        task_dir = os.path.join(self.temp_dir, "uuid-task")
        sender_dir = os.path.dirname(task_dir)
        all_media_dir = os.path.join(sender_dir, "All-Media")
        
        os.makedirs(task_dir, exist_ok=True)
        
        # Create test files
        source_file1 = os.path.join(task_dir, "source1.pdf")
        source_file2 = os.path.join(task_dir, "source2.pdf")
        output_file = os.path.join(task_dir, "output.pdf")
        
        with open(source_file1, 'w') as f:
            f.write("test source 1")
        with open(source_file2, 'w') as f:
            f.write("test source 2")
        with open(output_file, 'w') as f:
            f.write("test output")
        
        # Run cleanup
        source_files = ["source1.pdf", "source2.pdf"]
        output_files = [{"path": output_file, "sent_id": "output123"}]
        
        success, moved_count = cleanup_task_universal(task_dir, source_files, output_files)
        
        # Assert results
        assert success is True
        assert moved_count == 3
        assert os.path.exists(os.path.join(all_media_dir, "source1.pdf"))
        assert os.path.exists(os.path.join(all_media_dir, "source2.pdf"))
        assert os.path.exists(os.path.join(all_media_dir, "output123.pdf"))
        assert not os.path.exists(task_dir)
    
    def test_cleanup_task_universal_exception(self):
        """Test cleanup_task_universal with exception"""
        with mock.patch("os.makedirs", side_effect=Exception("Mock error")):
            success, moved_count = cleanup_task_universal("/fake/path", [], [])
            assert success is False
            assert moved_count == 0
    
    def test_get_file_extension_from_mimetype(self):
        """Test get_file_extension_from_mimetype function"""
        assert get_file_extension_from_mimetype("application/pdf") == ".pdf"
        assert get_file_extension_from_mimetype("image/jpeg") in [".jpg", ".jpeg", ".jpe"]
        assert get_file_extension_from_mimetype("text/plain") in [".txt", ".text"]
        assert get_file_extension_from_mimetype(None) == ".bin"
        assert get_file_extension_from_mimetype("application/unknown") == ".bin"