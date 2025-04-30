"""
Tests for the Redis persistence utility.
"""

import unittest
import os
import json
from unittest.mock import patch, MagicMock

from utils.persistence import RedisStateManager, get_state_manager
from app.exceptions import StateManagementError


class TestRedisPersistence(unittest.TestCase):
    """Test suite for Redis persistence functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock Redis client
        self.redis_mock = MagicMock()
        
        # Create a patcher for the Redis class
        self.redis_patcher = patch('utils.persistence.redis.Redis', return_value=self.redis_mock)
        self.mock_redis_class = self.redis_patcher.start()
        
        # Set up the state manager with mocked Redis
        self.state_manager = RedisStateManager()
        
        # Configure Redis mock to return values for certain calls
        self.redis_mock.ping.return_value = True
    
    def tearDown(self):
        """Tear down test fixtures."""
        self.redis_patcher.stop()
    
    def test_get_workflow_key(self):
        """Test generating the Redis key for a workflow."""
        sender_jid = "1234@whatsapp.net"
        expected_key = "doc_scanner:workflow:1234@whatsapp.net"
        
        key = self.state_manager.get_workflow_key(sender_jid)
        
        self.assertEqual(key, expected_key)
    
    def test_save_workflow_state(self):
        """Test saving workflow state."""
        sender_jid = "1234@whatsapp.net"
        workflow_state = {
            "task_id": "abc123",
            "workflow_type": "merge",
            "custom_field": "test"
        }
        
        # Configure mock to return True for setex
        self.redis_mock.setex.return_value = True
        
        result = self.state_manager.save_workflow_state(sender_jid, workflow_state)
        
        self.assertTrue(result)
        self.redis_mock.setex.assert_called_once()
        
        # Extract arguments from the call
        call_args = self.redis_mock.setex.call_args[0]
        
        # First arg should be the key
        self.assertEqual(call_args[0], f"doc_scanner:workflow:{sender_jid}")
        
        # Third arg should be the JSON string
        saved_json = json.loads(call_args[2])
        self.assertEqual(saved_json, workflow_state)
    
    def test_load_workflow_state(self):
        """Test loading workflow state."""
        sender_jid = "1234@whatsapp.net"
        workflow_state = {
            "task_id": "abc123",
            "workflow_type": "merge",
            "custom_field": "test"
        }
        
        # Configure mock to return a JSON string for get
        self.redis_mock.get.return_value = json.dumps(workflow_state)
        
        result = self.state_manager.load_workflow_state(sender_jid)
        
        self.assertEqual(result, workflow_state)
        self.redis_mock.get.assert_called_once_with(f"doc_scanner:workflow:{sender_jid}")
        
        # Verify that expire is called to refresh TTL
        self.redis_mock.expire.assert_called_once()
    
    def test_load_workflow_state_not_found(self):
        """Test loading workflow state when it doesn't exist."""
        sender_jid = "1234@whatsapp.net"
        
        # Configure mock to return None for get
        self.redis_mock.get.return_value = None
        
        result = self.state_manager.load_workflow_state(sender_jid)
        
        self.assertIsNone(result)
        self.redis_mock.get.assert_called_once_with(f"doc_scanner:workflow:{sender_jid}")
        
        # Verify that expire is not called when no state exists
        self.redis_mock.expire.assert_not_called()
    
    def test_delete_workflow_state(self):
        """Test deleting workflow state."""
        sender_jid = "1234@whatsapp.net"
        
        # Configure mock to return 1 for delete (key existed)
        self.redis_mock.delete.return_value = 1
        
        result = self.state_manager.delete_workflow_state(sender_jid)
        
        self.assertTrue(result)
        self.redis_mock.delete.assert_called_once_with(f"doc_scanner:workflow:{sender_jid}")
    
    def test_delete_workflow_state_not_found(self):
        """Test deleting workflow state when it doesn't exist."""
        sender_jid = "1234@whatsapp.net"
        
        # Configure mock to return 0 for delete (key didn't exist)
        self.redis_mock.delete.return_value = 0
        
        result = self.state_manager.delete_workflow_state(sender_jid)
        
        self.assertFalse(result)
        self.redis_mock.delete.assert_called_once_with(f"doc_scanner:workflow:{sender_jid}")
    
    def test_get_all_active_workflows(self):
        """Test getting all active workflows."""
        # Configure mock to return a list of keys
        self.redis_mock.keys.return_value = [
            "doc_scanner:workflow:1234@whatsapp.net",
            "doc_scanner:workflow:5678@whatsapp.net"
        ]
        
        # Configure mock to return workflow states for each key
        def get_side_effect(key):
            if "1234" in key:
                return json.dumps({"task_id": "abc123", "workflow_type": "merge"})
            elif "5678" in key:
                return json.dumps({"task_id": "def456", "workflow_type": "split"})
            return None
        
        self.redis_mock.get.side_effect = get_side_effect
        
        result = self.state_manager.get_all_active_workflows()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result["1234@whatsapp.net"]["task_id"], "abc123")
        self.assertEqual(result["5678@whatsapp.net"]["task_id"], "def456")
        
        # Verify keys was called once
        self.redis_mock.keys.assert_called_once_with("doc_scanner:workflow:*")
    
    def test_redis_error_handling(self):
        """Test error handling when Redis operations fail."""
        sender_jid = "1234@whatsapp.net"
        
        # Configure mock to raise an exception
        self.redis_mock.get.side_effect = Exception("Redis connection error")
        
        with self.assertRaises(StateManagementError):
            self.state_manager.load_workflow_state(sender_jid)

    @patch('utils.persistence._state_manager', None)
    def test_get_state_manager_singleton(self):
        """Test that get_state_manager returns a singleton instance."""
        # Patch the RedisStateManager.__init__ to avoid actual initialization
        with patch.object(RedisStateManager, '__init__', return_value=None):
            manager1 = get_state_manager()
            manager2 = get_state_manager()
            
            # Both calls should return the same instance
            self.assertIs(manager1, manager2)


class TestRedisStateManagerIntegration(unittest.TestCase):
    """
    Integration tests for RedisStateManager.
    
    These tests require a running Redis server. To run these tests:
    1. Make sure Redis is running locally on default port
    2. Run with: pytest -xvs tests/utils/test_persistence.py::TestRedisStateManagerIntegration
    
    Skip these if Redis is not available in the environment.
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up for all test cases."""
        import redis
        try:
            # Try to connect to Redis
            r = redis.Redis(host='localhost', port=6379, db=0)
            r.ping()
            cls.skip_tests = False
        except:
            cls.skip_tests = True
    
    def setUp(self):
        """Set up test fixtures."""
        if self.skip_tests:
            self.skipTest("Redis server not available")
        
        # Use a separate test database
        os.environ["REDIS_DB"] = "15"  # Use DB 15 for testing
        os.environ["REDIS_PREFIX"] = "test:"
        
        self.state_manager = RedisStateManager()
        
        # Clear any existing test data
        keys = self.state_manager.redis.keys("test:*")
        if keys:
            self.state_manager.redis.delete(*keys)
    
    def tearDown(self):
        """Tear down test fixtures."""
        if not self.skip_tests:
            # Clean up test data
            keys = self.state_manager.redis.keys("test:*")
            if keys:
                self.state_manager.redis.delete(*keys)
            
            # Reset environment variables
            if "REDIS_DB" in os.environ:
                del os.environ["REDIS_DB"]
            if "REDIS_PREFIX" in os.environ:
                del os.environ["REDIS_PREFIX"]
    
    def test_save_and_load_workflow(self):
        """Test saving and loading a workflow state from Redis."""
        sender_jid = "integration_test@whatsapp.net"
        workflow_state = {
            "task_id": "integration123",
            "workflow_type": "merge",
            "custom_field": "integration_test"
        }
        
        # Save the state
        result = self.state_manager.save_workflow_state(sender_jid, workflow_state)
        self.assertTrue(result)
        
        # Load the state
        loaded_state = self.state_manager.load_workflow_state(sender_jid)
        self.assertEqual(loaded_state, workflow_state)
    
    def test_delete_workflow(self):
        """Test deleting a workflow state from Redis."""
        sender_jid = "integration_test@whatsapp.net"
        workflow_state = {
            "task_id": "integration123",
            "workflow_type": "merge",
            "custom_field": "integration_test"
        }
        
        # Save the state
        self.state_manager.save_workflow_state(sender_jid, workflow_state)
        
        # Delete the state
        result = self.state_manager.delete_workflow_state(sender_jid)
        self.assertTrue(result)
        
        # Try to load the state
        loaded_state = self.state_manager.load_workflow_state(sender_jid)
        self.assertIsNone(loaded_state)