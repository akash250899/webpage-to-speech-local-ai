"""
Global In-Memory Job State Management
"""

import asyncio

# Global in-memory dictionary tracking job state and metadata
jobs = {}

# Lazily-initialized queue for background generation tasks. Created on first
# use (inside the running event loop) so it is not bound to a stale loop
# created at import time.
_task_queue = None


def get_task_queue() -> asyncio.Queue:
    """Return the shared task queue, creating it lazily on the running loop."""
    global _task_queue
    if _task_queue is None:
        _task_queue = asyncio.Queue()
    return _task_queue


