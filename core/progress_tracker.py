"""
Progress tracking system for download operations.
Manages SSE subscriptions and broadcasts progress updates.

Based on SERVER_MIGRATION_PLAN.md - Day 5
"""

import asyncio
from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ProgressTracker:
    """
    Tracks download progress for real-time updates via Server-Sent Events (SSE).
    
    Features:
    - Multiple subscribers per download_id
    - Automatic cleanup of completed downloads
    - Thread-safe progress updates
    """
    
    def __init__(self):
        self._progress: Dict[str, int] = {}  # download_id -> progress (0-100)
        self._status: Dict[str, str] = {}  # download_id -> status message
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}  # download_id -> list of queues
        self._completed: Dict[str, bool] = {}  # download_id -> completion flag
        self._errors: Dict[str, str] = {}  # download_id -> error message
        self._start_times: Dict[str, datetime] = {}  # download_id -> start timestamp
        self._lock = asyncio.Lock()
    
    async def start_download(self, download_id: str) -> None:
        """Initialize progress tracking for a new download"""
        async with self._lock:
            self._progress[download_id] = 0
            self._status[download_id] = "Starting download..."
            self._completed[download_id] = False
            self._start_times[download_id] = datetime.now()
            self._subscribers[download_id] = []
            logger.info(f"📊 Progress tracker initialized for {download_id}")
    
    async def set_progress(
        self, 
        download_id: str, 
        progress: int, 
        status: Optional[str] = None
    ) -> None:
        """
        Update progress and notify all subscribers.
        
        Args:
            download_id: Unique download identifier
            progress: Progress percentage (0-100)
            status: Optional status message
        """
        async with self._lock:
            self._progress[download_id] = min(100, max(0, progress))
            if status:
                self._status[download_id] = status
            
            # Notify all subscribers
            if download_id in self._subscribers:
                for queue in self._subscribers[download_id]:
                    try:
                        await queue.put({
                            'progress': self._progress[download_id],
                            'status': self._status[download_id],
                            'timestamp': datetime.now().isoformat()
                        })
                    except Exception as e:
                        logger.error(f"❌ Failed to notify subscriber: {e}")
            
            logger.debug(
                f"📈 Progress update: {download_id} -> {progress}% "
                f"({status or 'no status'})"
            )
    
    async def complete_download(
        self, 
        download_id: str, 
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """
        Mark download as complete and notify subscribers.
        
        Args:
            download_id: Unique download identifier
            success: Whether download succeeded
            error: Error message if failed
        """
        async with self._lock:
            self._completed[download_id] = True
            
            if success:
                self._progress[download_id] = 100
                self._status[download_id] = "Download complete!"
                elapsed = (datetime.now() - self._start_times.get(download_id, datetime.now())).total_seconds()
                logger.info(f"✅ Download {download_id} completed in {elapsed:.1f}s")
            else:
                self._errors[download_id] = error or "Unknown error"
                self._status[download_id] = f"Failed: {error}"
                logger.error(f"❌ Download {download_id} failed: {error}")
            
            # Send final notification to all subscribers
            if download_id in self._subscribers:
                final_message = {
                    'progress': self._progress[download_id],
                    'status': self._status[download_id],
                    'completed': True,
                    'success': success,
                    'timestamp': datetime.now().isoformat()
                }
                if error:
                    final_message['error'] = error
                
                for queue in self._subscribers[download_id]:
                    try:
                        await queue.put(final_message)
                    except Exception as e:
                        logger.error(f"❌ Failed to send completion notification: {e}")
    
    def get_progress(self, download_id: str) -> int:
        """Get current progress for download_id (synchronous)"""
        return self._progress.get(download_id, 0)
    
    def get_status(self, download_id: str) -> str:
        """Get current status message for download_id"""
        return self._status.get(download_id, "Unknown")
    
    def is_completed(self, download_id: str) -> bool:
        """Check if download is completed"""
        return self._completed.get(download_id, False)
    
    def get_error(self, download_id: str) -> Optional[str]:
        """Get error message if download failed"""
        return self._errors.get(download_id)
    
    async def subscribe(self, download_id: str) -> asyncio.Queue:
        """
        Subscribe to progress updates for a download (for SSE).
        
        Args:
            download_id: Unique download identifier
            
        Returns:
            asyncio.Queue that will receive progress updates
        """
        async with self._lock:
            queue = asyncio.Queue()
            
            if download_id not in self._subscribers:
                self._subscribers[download_id] = []
            
            self._subscribers[download_id].append(queue)
            
            # Send current state immediately
            if download_id in self._progress:
                await queue.put({
                    'progress': self._progress[download_id],
                    'status': self._status.get(download_id, "In progress..."),
                    'timestamp': datetime.now().isoformat()
                })
            
            logger.info(f"📡 New subscriber for {download_id} (total: {len(self._subscribers[download_id])})")
            return queue
    
    async def unsubscribe(self, download_id: str, queue: asyncio.Queue) -> None:
        """
        Unsubscribe from progress updates.
        
        Args:
            download_id: Unique download identifier
            queue: The queue to remove
        """
        async with self._lock:
            if download_id in self._subscribers:
                try:
                    self._subscribers[download_id].remove(queue)
                    logger.info(f"📡 Subscriber removed from {download_id}")
                except ValueError:
                    pass
    
    async def cleanup_old_downloads(self, max_age_hours: int = 24) -> int:
        """
        Remove tracking data for old downloads.
        
        Args:
            max_age_hours: Maximum age in hours to keep completed downloads
            
        Returns:
            Number of downloads cleaned up
        """
        async with self._lock:
            now = datetime.now()
            to_remove = []
            
            for download_id, start_time in self._start_times.items():
                age_hours = (now - start_time).total_seconds() / 3600
                if age_hours > max_age_hours and self._completed.get(download_id, False):
                    to_remove.append(download_id)
            
            for download_id in to_remove:
                # Clear all tracking data
                self._progress.pop(download_id, None)
                self._status.pop(download_id, None)
                self._completed.pop(download_id, None)
                self._errors.pop(download_id, None)
                self._start_times.pop(download_id, None)
                self._subscribers.pop(download_id, None)
            
            if to_remove:
                logger.info(f"🧹 Cleaned up {len(to_remove)} old download(s)")
            
            return len(to_remove)
    
    def get_active_downloads(self) -> List[str]:
        """Get list of active (non-completed) download IDs"""
        return [
            download_id 
            for download_id, completed in self._completed.items() 
            if not completed
        ]
    
    def get_stats(self) -> Dict:
        """Get tracker statistics for monitoring"""
        return {
            'total_downloads': len(self._progress),
            'active_downloads': len(self.get_active_downloads()),
            'completed_downloads': sum(1 for c in self._completed.values() if c),
            'failed_downloads': len(self._errors),
            'total_subscribers': sum(len(subs) for subs in self._subscribers.values())
        }
