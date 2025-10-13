# nodes/core/base_node.py
"""
Base Node class with built-in observability, error handling, and monitoring
All your nodes should inherit from this class
"""

import asyncio
import os
import time
import sys
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime
import functools
import inspect
sys.path.append(os.getcwd())  # Fixed - use getcwd() not chdir
from utils.logger_wrapper import setup_logger
# Setup logging
logger = setup_logger(name="BaseNode")
class BaseNode(ABC):
    """
    Base class for all workflow nodes
    
    Features:
    - Automatic logging with context
    - Performance timing
    - Error handling with retry
    - Metrics collection
    - Async/sync support
    
    Usage:
        class MyNode(BaseNode):
            async def execute(self, state):
                # Your logic here
                return state
    """
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logger
        self.metrics = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "total_duration_ms": 0.0,
            "avg_duration_ms": 0.0,
            "min_duration_ms": float('inf'),
            "max_duration_ms": 0.0
        }
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point - LangGraph calls this
        Supports both sync and async execute methods
        """
        # FIXED: Check if execute is async using inspect
        if inspect.iscoroutinefunction(self.execute):
            # Async execute method
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in event loop, create task
                    return asyncio.create_task(self._execute_with_monitoring(state))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(self._execute_with_monitoring(state))
        else:
            # Sync execute method
            return self._execute_with_monitoring_sync(state)
    
    @abstractmethod
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Override this method in your node
        Can be async or sync (just remove async keyword)
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state
        """
        pass
    
    async def _execute_with_monitoring(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Internal method that adds monitoring to async execute"""
        start_time = time.time()
        
        # Log start
        self._log_start(state)
        
        try:
            # Execute the actual node logic
            result = await self.execute(state)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log success
            self._log_complete(state, duration_ms)
            
            # Update metrics
            self._update_metrics(duration_ms, success=True)
            
            # Add timing to state
            result = self._update_state_timing(result, duration_ms)
            
            return result
        
        except Exception as e:
            # Calculate duration even on error
            duration_ms = (time.time() - start_time) * 1000
            
            # Log error
            self._log_error(state, e, duration_ms)
            
            # Update metrics
            self._update_metrics(duration_ms, success=False)
            
            # Add error to state
            state = self._add_error_to_state(state, e)
            
            # Re-raise exception
            raise
    
    def _execute_with_monitoring_sync(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Internal method that adds monitoring to sync execute"""
        start_time = time.time()
        
        # Log start
        self._log_start(state)
        
        try:
            # FIXED: Check if execute is actually async before calling
            if inspect.iscoroutinefunction(self.execute):
                raise RuntimeError(
                    f"Node {self.name} has async execute() but was called synchronously. "
                    "This should not happen - check __call__ implementation."
                )
            
            # Execute the actual node logic (sync)
            result = self.execute(state)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log success
            self._log_complete(state, duration_ms)
            
            # Update metrics
            self._update_metrics(duration_ms, success=True)
            
            # Add timing to state
            result = self._update_state_timing(result, duration_ms)
            
            return result
        
        except Exception as e:
            # Calculate duration even on error
            duration_ms = (time.time() - start_time) * 1000
            
            # Log error
            self._log_error(state, e, duration_ms)
            
            # Update metrics
            self._update_metrics(duration_ms, success=False)
            
            # Add error to state
            state = self._add_error_to_state(state, e)
            
            # Re-raise exception
            raise
    
    def _log_start(self, state: Dict[str, Any]):
        """Log node execution start"""
        self.logger.info(
            f"[{self.name}] Starting execution",
            extra={
                "session_id": state.get("session_id"),
                "lead_id": state.get("lead_id"),
                "intent": state.get("detected_intent"),
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def _log_complete(self, state: Dict[str, Any], duration_ms: float):
        """Log node execution completion"""
        self.logger.info(
            f"[{self.name}] Completed successfully",
            extra={
                "session_id": state.get("session_id"),
                "duration_ms": round(duration_ms, 2),
                "actions_pending": len(state.get("pending_actions", [])),
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def _log_error(self, state: Dict[str, Any], error: Exception, duration_ms: float):
        """Log node execution error"""
        self.logger.error(
            f"[{self.name}] Execution failed",
            extra={
                "session_id": state.get("session_id"),
                "error": str(error),
                "error_type": type(error).__name__,
                "duration_ms": round(duration_ms, 2),
                "timestamp": datetime.utcnow().isoformat()
            },
            exc_info=True
        )
    
    def _update_metrics(self, duration_ms: float, success: bool):
        """Update node performance metrics"""
        self.metrics["total_executions"] += 1
        
        if success:
            self.metrics["successful_executions"] += 1
        else:
            self.metrics["failed_executions"] += 1
        
        self.metrics["total_duration_ms"] += duration_ms
        self.metrics["avg_duration_ms"] = (
            self.metrics["total_duration_ms"] / self.metrics["total_executions"]
        )
        self.metrics["min_duration_ms"] = min(self.metrics["min_duration_ms"], duration_ms)
        self.metrics["max_duration_ms"] = max(self.metrics["max_duration_ms"], duration_ms)
    
    def _update_state_timing(
        self, 
        state: Dict[str, Any], 
        duration_ms: float
    ) -> Dict[str, Any]:
        """Add timing information to state"""
        if "node_execution_times" not in state:
            state["node_execution_times"] = {}
        
        state["node_execution_times"][self.name] = duration_ms
        state["total_processing_time"] = state.get("total_processing_time", 0.0) + duration_ms
        
        return state
    
    def _add_error_to_state(
        self, 
        state: Dict[str, Any], 
        error: Exception
    ) -> Dict[str, Any]:
        """Add error information to state"""
        if "errors" not in state:
            state["errors"] = []
        
        state["errors"].append({
            "node": self.name,
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        state["retry_count"] = state.get("retry_count", 0) + 1
        
        return state
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get node performance metrics"""
        return {
            "node_name": self.name,
            **self.metrics,
            "success_rate": (
                self.metrics["successful_executions"] / self.metrics["total_executions"]
                if self.metrics["total_executions"] > 0 else 0
            )
        }
    
    def reset_metrics(self):
        """Reset all metrics (useful for testing)"""
        self.metrics = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "total_duration_ms": 0.0,
            "avg_duration_ms": 0.0,
            "min_duration_ms": float('inf'),
            "max_duration_ms": 0.0
        }


# ============================================================================
# ENHANCED BASE CLASSES (Optional - for advanced use cases)
# ============================================================================

class BaseNodeWithRetry(BaseNode):
    """
    Base node with automatic retry logic
    Use this when your node calls external APIs that might fail
    """
    
    def __init__(self, name: str, max_retries: int = 3, retry_delay: float = 1.0):
        super().__init__(name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    async def execute_with_retry(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute with automatic retry on failure"""
        
        for attempt in range(self.max_retries):
            try:
                return await self.execute(state)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    # Last attempt failed, raise
                    raise
                
                # Wait before retry (exponential backoff)
                wait_time = self.retry_delay * (2 ** attempt)
                self.logger.warning(
                    f"[{self.name}] Attempt {attempt + 1} failed, retrying in {wait_time}s",
                    extra={"error": str(e)}
                )
                await asyncio.sleep(wait_time)


class BaseNodeWithCache(BaseNode):
    """
    Base node with caching support
    Use this for nodes that query external APIs with cacheable results
    """
    
    def __init__(self, name: str, cache_ttl: int = 3600):
        super().__init__(name)
        self.cache: Dict[str, Dict] = {}
        self.cache_ttl = cache_ttl  # seconds
    
    def _get_cache_key(self, state: Dict[str, Any]) -> str:
        """Generate cache key from state - override in subclass"""
        return state.get("current_message", "")
    
    def _get_cached(self, key: str) -> Optional[Dict]:
        """Get from cache if not expired"""
        if key in self.cache:
            cached = self.cache[key]
            cache_time = datetime.fromisoformat(cached["timestamp"])
            
            if (datetime.utcnow() - cache_time).seconds < self.cache_ttl:
                self.logger.info(f"Cache hit for key: {key[:20]}...")
                return cached["data"]
            else:
                # Expired, remove
                del self.cache[key]
                self.logger.info(f"Cache expired for key: {key[:20]}...")
        
        return None
    
    def _set_cache(self, key: str, data: Dict):
        """Store in cache"""
        self.cache[key] = {
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.logger.info(f"Cached data for key: {key[:20]}...")
    
    def clear_cache(self):
        """Clear all cache"""
        self.cache.clear()
        self.logger.info("Cache cleared")


def with_timing(func):
    """
    Decorator for timing async functions
    Usage:
        @with_timing
        async def my_function(self, state):
            ...
    """
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        start_time = time.time()
        try:
            result = await func(self, *args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            self.logger.info(f"[{self.name}] Completed in {duration_ms:.2f}ms")
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error(f"[{self.name}] Failed after {duration_ms:.2f}ms: {e}")
            raise
    return wrapper


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    """
    Example showing how to use BaseNode
    """
    
    # Example 1: Simple async node
    class ExampleAsyncNode(BaseNode):
        async def execute(self, state):
            self.logger.info("Doing some async work...")
            await asyncio.sleep(0.1)  # Simulate async operation
            
            state["completed_actions"] = state.get("completed_actions", [])
            state["completed_actions"].append("example_action")
            
            return state
    
    # Example 2: Simple sync node
    class ExampleSyncNode(BaseNode):
        def execute(self, state):
            self.logger.info("Doing some sync work...")
            time.sleep(0.1)  # Simulate work
            
            state["completed_actions"] = state.get("completed_actions", [])
            state["completed_actions"].append("sync_action")
            
            return state
    
    # Example 3: Node with retry
    class ExampleRetryNode(BaseNodeWithRetry):
        def __init__(self):
            super().__init__("retry_example", max_retries=3, retry_delay=0.5)
        
        async def execute(self, state):
            # Simulate random failures for testing
            import random
            if random.random() < 0.5:
                raise Exception("Random failure for testing")
            
            state["retry_success"] = True
            return state
    
    # Test the nodes
    async def test_nodes():
        print("\n" + "="*60)
        print("Testing BaseNode Examples")
        print("="*60 + "\n")
        
        # Test async node
        async_node = ExampleAsyncNode("test_async")
        test_state = {
            "session_id": "test_123",
            "lead_id": "lead_456",
            "completed_actions": [],
            "node_execution_times": {},
            "total_processing_time": 0.0,
            "errors": [],
            "retry_count": 0
        }
        
        result = async_node(test_state)
        print(f"Async node result: {result['completed_actions']}")
        print(f"Execution time: {result['node_execution_times']['test_async']:.2f}ms")
        print(f"Metrics: {async_node.get_metrics()}\n")
        
        # Test sync node
        sync_node = ExampleSyncNode("test_sync")
        result = sync_node(result)
        print(f"Sync node result: {result['completed_actions']}")
        print(f"Execution time: {result['node_execution_times']['test_sync']:.2f}ms")
        print(f"Metrics: {sync_node.get_metrics()}\n")
        
        print("="*60)
        print("All tests passed!")
        print("="*60 + "\n")
    
    # Run tests
    asyncio.run(test_nodes())