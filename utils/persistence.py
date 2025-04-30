"""
Persistence utilities for the Document Scanner application.

This module provides functionality for persisting workflow state using Redis.
"""

import json
import logging
import os
from typing import Dict, Any, Optional, Union, List

import redis
from redis.exceptions import RedisError

from app.exceptions import StateManagementError
from utils.logging_utils import setup_logger
from config.settings import (
    REDIS_ENABLED,
    REDIS_HOST, 
    REDIS_PORT, 
    REDIS_DB, 
    REDIS_PASSWORD,
    REDIS_PREFIX,
    REDIS_TIMEOUT,
    WORKFLOW_STATE_TTL
)

# Set up logger
logger = setup_logger(__name__)

class InMemoryStateManager:
    """
    Simple in-memory state manager for workflow states.
    Used as a fallback when Redis is not available.
    """
    
    def __init__(self):
        """Initialize in-memory storage."""
        self.storage = {}
        logger.info("Using in-memory state manager")
    
    def save_workflow_state(self, sender_jid: str, state_data: Dict[str, Any]) -> bool:
        """
        Save workflow state to memory.
        
        Args:
            sender_jid: User's JID
            state_data: Workflow state to save
            
        Returns:
            True on success
        """
        self.storage[sender_jid] = state_data.copy()
        logger.debug(f"Saved workflow state for {sender_jid} in memory")
        return True
    
    def load_workflow_state(self, sender_jid: str) -> Optional[Dict[str, Any]]:
        """
        Load workflow state from memory.
        
        Args:
            sender_jid: User's JID
            
        Returns:
            Workflow state or None if not found
        """
        state = self.storage.get(sender_jid)
        if state:
            logger.debug(f"Loaded workflow state for {sender_jid} from memory")
            return state.copy()
        logger.debug(f"No workflow state found for {sender_jid} in memory")
        return None
    
    def delete_workflow_state(self, sender_jid: str) -> bool:
        """
        Delete workflow state from memory.
        
        Args:
            sender_jid: User's JID
            
        Returns:
            True if state existed, False otherwise
        """
        if sender_jid in self.storage:
            del self.storage[sender_jid]
            logger.debug(f"Deleted workflow state for {sender_jid} from memory")
            return True
        logger.debug(f"No workflow state to delete for {sender_jid} from memory")
        return False
    
    def get_all_active_workflows(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all active workflows from memory.
        
        Returns:
            Dictionary mapping JIDs to workflow states
        """
        return {jid: state.copy() for jid, state in self.storage.items()}
    
    def ping(self) -> bool:
        """
        Check if storage is available.
        
        Returns:
            Always True for in-memory storage
        """
        return True

class RedisStateManager:
    """
    Manages the persistence of workflow state using Redis.
    """
    
    def __init__(self) -> None:
        """
        Initialize Redis connection.
        """
        try:
            self.redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                socket_timeout=REDIS_TIMEOUT,
                socket_connect_timeout=REDIS_TIMEOUT,
                decode_responses=True  # Automatically decode responses to strings
            )
            # Test connection
            self.redis.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except (RedisError, Exception) as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            raise StateManagementError(f"Failed to connect to Redis: {str(e)}")
    
    def get_workflow_key(self, sender_jid: str) -> str:
        """
        Generate a Redis key for a specific user's workflow state.
        
        Args:
            sender_jid: User's JID
            
        Returns:
            Redis key string
        """
        return f"{REDIS_PREFIX}workflow:{sender_jid}"
    
    def save_workflow_state(self, sender_jid: str, state_data: Dict[str, Any]) -> bool:
        """
        Persist workflow state for a user.
        
        Args:
            sender_jid: User's JID
            state_data: Workflow state to save
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            StateManagementError: If Redis operation fails
        """
        key = self.get_workflow_key(sender_jid)
        
        try:
            # Convert the state data to JSON string
            json_data = json.dumps(state_data)
            # Store in Redis with expiration
            result = self.redis.setex(key, WORKFLOW_STATE_TTL, json_data)
            
            if result:
                logger.debug(f"Saved workflow state for {sender_jid}")
            else:
                logger.warning(f"Failed to save workflow state for {sender_jid}")
            
            return bool(result)
        
        except (RedisError, TypeError, ValueError, Exception) as e:
            error_msg = f"Error saving workflow state for {sender_jid}: {str(e)}"
            logger.error(error_msg)
            raise StateManagementError(error_msg)
    
    def load_workflow_state(self, sender_jid: str) -> Optional[Dict[str, Any]]:
        """
        Load workflow state for a user.
        
        Args:
            sender_jid: User's JID
            
        Returns:
            Workflow state dictionary, or None if no state exists
            
        Raises:
            StateManagementError: If Redis operation fails
        """
        key = self.get_workflow_key(sender_jid)
        
        try:
            json_data = self.redis.get(key)
            
            if not json_data:
                logger.debug(f"No workflow state found for {sender_jid}")
                return None
            
            # Parse JSON data back to dictionary
            state_data = json.loads(json_data)
            logger.debug(f"Loaded workflow state for {sender_jid}")
            
            # Refresh TTL when loading state
            self.redis.expire(key, WORKFLOW_STATE_TTL)
            
            return state_data
        
        except (RedisError, json.JSONDecodeError, Exception) as e:
            error_msg = f"Error loading workflow state for {sender_jid}: {str(e)}"
            logger.error(error_msg)
            raise StateManagementError(error_msg)
    
    def delete_workflow_state(self, sender_jid: str) -> bool:
        """
        Delete workflow state for a user.
        
        Args:
            sender_jid: User's JID
            
        Returns:
            True if successful, False if no state existed
            
        Raises:
            StateManagementError: If Redis operation fails
        """
        key = self.get_workflow_key(sender_jid)
        
        try:
            result = self.redis.delete(key)
            
            if result:
                logger.debug(f"Deleted workflow state for {sender_jid}")
            else:
                logger.debug(f"No workflow state to delete for {sender_jid}")
            
            return bool(result)
        
        except (RedisError, Exception) as e:
            error_msg = f"Error deleting workflow state for {sender_jid}: {str(e)}"
            logger.error(error_msg)
            raise StateManagementError(error_msg)
    
    def get_all_active_workflows(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all active workflow states from Redis.
        
        Returns:
            Dictionary mapping user JIDs to their workflow states
            
        Raises:
            StateManagementError: If Redis operation fails
        """
        try:
            # Get all keys matching the workflow pattern
            pattern = f"{REDIS_PREFIX}workflow:*"
            all_keys = self.redis.keys(pattern)
            
            result = {}
            for key in all_keys:
                # Extract JID from key
                jid = key.replace(f"{REDIS_PREFIX}workflow:", "")
                # Get state for this JID
                state = self.load_workflow_state(jid)
                if state:
                    result[jid] = state
            
            return result
        
        except (RedisError, Exception) as e:
            error_msg = f"Error getting all workflow states: {str(e)}"
            logger.error(error_msg)
            raise StateManagementError(error_msg)
    
    def ping(self) -> bool:
        """
        Check if Redis connection is working.
        
        Returns:
            True if connection is active
            
        Raises:
            StateManagementError: If Redis operation fails
        """
        try:
            return bool(self.redis.ping())
        except (RedisError, Exception) as e:
            error_msg = f"Redis connection failed: {str(e)}"
            logger.error(error_msg)
            raise StateManagementError(error_msg)


# Singleton instance
_state_manager = None

def get_state_manager():
    """
    Get or create a state manager singleton instance.
    
    Returns:
        RedisStateManager if Redis is enabled and connection successful,
        InMemoryStateManager otherwise
    """
    global _state_manager
    
    if _state_manager is None:
        # Try to use Redis if enabled
        if REDIS_ENABLED:
            try:
                _state_manager = RedisStateManager()
                logger.info("Using Redis for state persistence")
            except StateManagementError as e:
                logger.warning(f"Failed to initialize Redis state manager: {str(e)}")
                logger.warning("Falling back to in-memory state manager")
                _state_manager = InMemoryStateManager()
        else:
            logger.info("Redis is disabled, using in-memory state manager")
            _state_manager = InMemoryStateManager()
    
    return _state_manager