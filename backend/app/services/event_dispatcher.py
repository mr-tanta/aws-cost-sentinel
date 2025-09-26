import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
import structlog

from app.services.websocket_service import websocket_manager
from app.services.cache_service import cache_service
from app.services.queue_service import queue_service, JobStatus

logger = structlog.get_logger(__name__)


class EventDispatcher:
    """Centralized event dispatcher for real-time notifications"""

    def __init__(self):
        self.event_handlers = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default event handlers"""
        self.event_handlers.update({
            "cost_data_updated": self._handle_cost_data_updated,
            "waste_items_detected": self._handle_waste_items_detected,
            "recommendations_generated": self._handle_recommendations_generated,
            "job_status_changed": self._handle_job_status_changed,
            "account_status_changed": self._handle_account_status_changed,
            "sync_completed": self._handle_sync_completed,
            "error_occurred": self._handle_error_occurred
        })

    def register_handler(self, event_type: str, handler):
        """Register custom event handler"""
        self.event_handlers[event_type] = handler
        logger.info("Event handler registered", event_type=event_type)

    async def dispatch(self, event_type: str, data: Dict[str, Any]):
        """Dispatch event to registered handlers"""
        if event_type not in self.event_handlers:
            logger.warning("No handler registered for event", event_type=event_type)
            return

        try:
            handler = self.event_handlers[event_type]
            await handler(data)

            # Cache recent events for debugging
            await self._cache_event(event_type, data)

        except Exception as e:
            logger.error("Event handler failed",
                        event_type=event_type,
                        error=str(e))

    async def _cache_event(self, event_type: str, data: Dict[str, Any]):
        """Cache recent events for debugging and analytics"""
        try:
            event_record = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Store in Redis with short TTL
            cache_key = f"recent_events:{event_type}"
            cache_service.set(cache_key, event_record, expire=3600)  # 1 hour

        except Exception as e:
            logger.error("Failed to cache event", error=str(e))

    # Event Handlers

    async def _handle_cost_data_updated(self, data: Dict[str, Any]):
        """Handle cost data update event"""
        user_id = data.get("user_id")
        account_id = data.get("account_id")
        cost_data = data.get("cost_data", {})

        if not user_id or not account_id:
            logger.warning("Missing required fields for cost data update")
            return

        # Send WebSocket notification
        await websocket_manager.send_cost_update(
            user_id=user_id,
            account_id=account_id,
            cost_data=cost_data
        )

        # Invalidate related cache entries
        cache_service.invalidate_account_cache(account_id)

        logger.info("Cost data update event processed",
                   user_id=user_id,
                   account_id=account_id)

    async def _handle_waste_items_detected(self, data: Dict[str, Any]):
        """Handle waste detection event"""
        user_id = data.get("user_id")
        account_id = data.get("account_id")
        waste_items = data.get("waste_items", [])

        if not user_id or not account_id:
            logger.warning("Missing required fields for waste detection")
            return

        # Send WebSocket notification
        await websocket_manager.send_waste_detection(
            user_id=user_id,
            account_id=account_id,
            waste_items=waste_items
        )

        # Cache waste scan results
        cache_service.cache_waste_scan_results(
            account_id=account_id,
            scan_results={
                "items": waste_items,
                "detected_at": datetime.utcnow().isoformat(),
                "total_items": len(waste_items)
            }
        )

        logger.info("Waste detection event processed",
                   user_id=user_id,
                   account_id=account_id,
                   items_count=len(waste_items))

    async def _handle_recommendations_generated(self, data: Dict[str, Any]):
        """Handle recommendations generation event"""
        user_id = data.get("user_id")
        account_id = data.get("account_id")
        recommendations = data.get("recommendations", [])

        if not user_id:
            logger.warning("Missing user_id for recommendations event")
            return

        # Send WebSocket notification
        await websocket_manager.send_recommendation_update(
            user_id=user_id,
            account_id=account_id or "all",
            recommendations=recommendations
        )

        # Cache recommendations
        if account_id:
            cache_service.cache_recommendations(
                account_id=account_id,
                recommendations=recommendations
            )

        logger.info("Recommendations event processed",
                   user_id=user_id,
                   account_id=account_id,
                   recommendations_count=len(recommendations))

    async def _handle_job_status_changed(self, data: Dict[str, Any]):
        """Handle job status change event"""
        user_id = data.get("user_id")
        job_id = data.get("job_id")
        status = data.get("status")
        progress = data.get("progress")

        if not user_id or not job_id or not status:
            logger.warning("Missing required fields for job status change")
            return

        # Send WebSocket notification
        await websocket_manager.send_job_status_update(
            user_id=user_id,
            job_id=job_id,
            status=status,
            progress=progress
        )

        logger.info("Job status change event processed",
                   user_id=user_id,
                   job_id=job_id,
                   status=status)

    async def _handle_account_status_changed(self, data: Dict[str, Any]):
        """Handle account status change event"""
        user_id = data.get("user_id")
        account_id = data.get("account_id")
        status = data.get("status")
        health_data = data.get("health_data")

        if not user_id or not account_id or not status:
            logger.warning("Missing required fields for account status change")
            return

        # Send WebSocket notification
        await websocket_manager.send_account_status_update(
            user_id=user_id,
            account_id=account_id,
            status=status,
            health_data=health_data
        )

        # Invalidate account cache if status is error
        if status in ["error", "disconnected"]:
            cache_service.invalidate_account_cache(account_id)

        logger.info("Account status change event processed",
                   user_id=user_id,
                   account_id=account_id,
                   status=status)

    async def _handle_sync_completed(self, data: Dict[str, Any]):
        """Handle sync completion event"""
        user_id = data.get("user_id")
        account_id = data.get("account_id")
        sync_type = data.get("sync_type", "cost")
        results = data.get("results", {})

        if not user_id or not account_id:
            logger.warning("Missing required fields for sync completion")
            return

        # Trigger relevant updates based on sync type
        if sync_type == "cost":
            await self.dispatch("cost_data_updated", {
                "user_id": user_id,
                "account_id": account_id,
                "cost_data": results
            })

        elif sync_type == "waste":
            await self.dispatch("waste_items_detected", {
                "user_id": user_id,
                "account_id": account_id,
                "waste_items": results.get("items", [])
            })

        logger.info("Sync completion event processed",
                   user_id=user_id,
                   account_id=account_id,
                   sync_type=sync_type)

    async def _handle_error_occurred(self, data: Dict[str, Any]):
        """Handle error event"""
        user_id = data.get("user_id")
        error_type = data.get("error_type")
        error_message = data.get("error_message")
        context = data.get("context", {})

        if not user_id:
            logger.warning("Missing user_id for error event")
            return

        # Send error notification via WebSocket
        await websocket_manager.send_personal_message(user_id, {
            "type": "error",
            "error_type": error_type,
            "message": error_message,
            "context": context,
            "timestamp": datetime.utcnow().isoformat()
        })

        logger.error("Error event processed",
                    user_id=user_id,
                    error_type=error_type,
                    error_message=error_message)

    # Batch event processing

    async def dispatch_batch(self, events: List[Dict[str, Any]]):
        """Dispatch multiple events in batch"""
        tasks = []
        for event in events:
            event_type = event.get("type")
            event_data = event.get("data", {})

            if event_type:
                task = asyncio.create_task(self.dispatch(event_type, event_data))
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # Convenience methods for common events

    async def notify_cost_sync_completed(
        self,
        user_id: str,
        account_id: str,
        cost_summary: Dict[str, Any]
    ):
        """Convenience method for cost sync completion"""
        await self.dispatch("cost_data_updated", {
            "user_id": user_id,
            "account_id": account_id,
            "cost_data": cost_summary
        })

    async def notify_waste_scan_completed(
        self,
        user_id: str,
        account_id: str,
        waste_items: List[Dict[str, Any]]
    ):
        """Convenience method for waste scan completion"""
        await self.dispatch("waste_items_detected", {
            "user_id": user_id,
            "account_id": account_id,
            "waste_items": waste_items
        })

    async def notify_recommendations_ready(
        self,
        user_id: str,
        account_id: Optional[str],
        recommendations: List[Dict[str, Any]]
    ):
        """Convenience method for recommendations ready"""
        await self.dispatch("recommendations_generated", {
            "user_id": user_id,
            "account_id": account_id,
            "recommendations": recommendations
        })

    async def notify_job_progress(
        self,
        user_id: str,
        job_id: str,
        status: str,
        progress: Optional[Dict[str, Any]] = None
    ):
        """Convenience method for job progress updates"""
        await self.dispatch("job_status_changed", {
            "user_id": user_id,
            "job_id": job_id,
            "status": status,
            "progress": progress or {}
        })

    async def notify_error(
        self,
        user_id: str,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Convenience method for error notifications"""
        await self.dispatch("error_occurred", {
            "user_id": user_id,
            "error_type": error_type,
            "error_message": error_message,
            "context": context or {}
        })

    # Analytics and monitoring

    async def get_recent_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent events for monitoring"""
        events = []

        try:
            if event_type:
                # Get specific event type
                cache_key = f"recent_events:{event_type}"
                event_data = cache_service.get(cache_key)
                if event_data:
                    events.append(event_data)
            else:
                # Get all recent events (this is simplified)
                # In production, you'd maintain a proper event log
                pass

        except Exception as e:
            logger.error("Failed to get recent events", error=str(e))

        return events[:limit]


# Global event dispatcher instance
event_dispatcher = EventDispatcher()