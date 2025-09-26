import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from enum import Enum
import structlog
from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis

from app.core.config import settings
from app.services.cache_service import cache_service

logger = structlog.get_logger(__name__)


class MessageType(Enum):
    """WebSocket message types"""
    COST_UPDATE = "cost_update"
    WASTE_DETECTED = "waste_detected"
    RECOMMENDATION_READY = "recommendation_ready"
    JOB_STATUS = "job_status"
    ACCOUNT_STATUS = "account_status"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class WebSocketManager:
    """Manages WebSocket connections and real-time messaging"""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.user_connections: Dict[str, Set[str]] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self.redis_client = None
        self.pubsub = None
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection for pub/sub"""
        try:
            self.redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            logger.info("WebSocket Redis client initialized")
        except Exception as e:
            logger.error("Failed to initialize WebSocket Redis client", error=str(e))

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        connection_id: str,
        filters: Optional[Dict[str, Any]] = None
    ):
        """Accept WebSocket connection and register it"""
        await websocket.accept()

        # Store connection
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

        # Track user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)

        # Store connection metadata
        self.connection_metadata[connection_id] = {
            "user_id": user_id,
            "websocket": websocket,
            "connected_at": datetime.utcnow().isoformat(),
            "filters": filters or {},
            "last_ping": datetime.utcnow().isoformat()
        }

        logger.info("WebSocket connection established",
                   user_id=user_id,
                   connection_id=connection_id,
                   total_connections=len(self.connection_metadata))

        # Send welcome message
        await self.send_personal_message(user_id, {
            "type": MessageType.PING.value,
            "message": "Connected successfully",
            "server_time": datetime.utcnow().isoformat()
        })

        # Start Redis subscription for this user
        asyncio.create_task(self._subscribe_to_redis_channels(user_id))

    async def disconnect(self, user_id: str, connection_id: str):
        """Remove WebSocket connection"""
        try:
            # Remove from active connections
            if user_id in self.active_connections:
                # Find and remove the specific websocket
                connections_to_remove = []
                for i, ws in enumerate(self.active_connections[user_id]):
                    if connection_id in self.connection_metadata:
                        metadata = self.connection_metadata[connection_id]
                        if metadata.get("websocket") is ws:
                            connections_to_remove.append(i)

                # Remove connections in reverse order to maintain indices
                for i in reversed(connections_to_remove):
                    del self.active_connections[user_id][i]

                # Clean up empty lists
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]

            # Remove from user connections
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(connection_id)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

            # Remove connection metadata
            if connection_id in self.connection_metadata:
                del self.connection_metadata[connection_id]

            logger.info("WebSocket connection closed",
                       user_id=user_id,
                       connection_id=connection_id,
                       remaining_connections=len(self.connection_metadata))

        except Exception as e:
            logger.error("Error during WebSocket disconnect",
                        user_id=user_id,
                        connection_id=connection_id,
                        error=str(e))

    async def send_personal_message(
        self,
        user_id: str,
        message: Dict[str, Any],
        connection_id: Optional[str] = None
    ):
        """Send message to specific user's connections"""
        if user_id not in self.active_connections:
            return

        message["timestamp"] = datetime.utcnow().isoformat()
        message_text = json.dumps(message)

        connections_to_remove = []

        for i, websocket in enumerate(self.active_connections[user_id]):
            try:
                # If connection_id is specified, only send to that connection
                if connection_id:
                    metadata = None
                    for conn_id, meta in self.connection_metadata.items():
                        if meta.get("websocket") is websocket and conn_id == connection_id:
                            metadata = meta
                            break
                    if not metadata:
                        continue

                # Check if message matches user's filters
                if not self._message_matches_filters(message, user_id, websocket):
                    continue

                await websocket.send_text(message_text)

            except WebSocketDisconnect:
                connections_to_remove.append(i)
            except Exception as e:
                logger.error("Error sending WebSocket message",
                           user_id=user_id,
                           error=str(e))
                connections_to_remove.append(i)

        # Clean up broken connections
        for i in reversed(connections_to_remove):
            del self.active_connections[user_id][i]

    async def broadcast_message(
        self,
        message: Dict[str, Any],
        user_filter: Optional[callable] = None
    ):
        """Broadcast message to all connected users"""
        message["timestamp"] = datetime.utcnow().isoformat()

        for user_id in list(self.active_connections.keys()):
            if user_filter and not user_filter(user_id):
                continue

            await self.send_personal_message(user_id, message)

    async def send_cost_update(
        self,
        user_id: str,
        account_id: str,
        cost_data: Dict[str, Any]
    ):
        """Send cost update notification"""
        message = {
            "type": MessageType.COST_UPDATE.value,
            "account_id": account_id,
            "data": cost_data,
            "message": f"Cost data updated for account {account_id}"
        }

        await self.send_personal_message(user_id, message)

        # Also publish to Redis for other instances
        await self._publish_to_redis(f"user:{user_id}:cost_updates", message)

    async def send_waste_detection(
        self,
        user_id: str,
        account_id: str,
        waste_items: List[Dict[str, Any]]
    ):
        """Send waste detection notification"""
        message = {
            "type": MessageType.WASTE_DETECTED.value,
            "account_id": account_id,
            "items_count": len(waste_items),
            "data": waste_items[:5],  # Send first 5 items
            "message": f"Found {len(waste_items)} waste items in account {account_id}"
        }

        await self.send_personal_message(user_id, message)
        await self._publish_to_redis(f"user:{user_id}:waste_detection", message)

    async def send_recommendation_update(
        self,
        user_id: str,
        account_id: str,
        recommendations: List[Dict[str, Any]]
    ):
        """Send recommendation update notification"""
        total_savings = sum(rec.get("estimated_savings", 0) for rec in recommendations)

        message = {
            "type": MessageType.RECOMMENDATION_READY.value,
            "account_id": account_id,
            "recommendations_count": len(recommendations),
            "total_potential_savings": total_savings,
            "data": recommendations[:3],  # Send top 3 recommendations
            "message": f"New recommendations available for account {account_id}"
        }

        await self.send_personal_message(user_id, message)
        await self._publish_to_redis(f"user:{user_id}:recommendations", message)

    async def send_job_status_update(
        self,
        user_id: str,
        job_id: str,
        status: str,
        progress: Optional[Dict[str, Any]] = None
    ):
        """Send job status update"""
        message = {
            "type": MessageType.JOB_STATUS.value,
            "job_id": job_id,
            "status": status,
            "progress": progress or {},
            "message": f"Job {job_id} status: {status}"
        }

        await self.send_personal_message(user_id, message)
        await self._publish_to_redis(f"user:{user_id}:job_status", message)

    async def send_account_status_update(
        self,
        user_id: str,
        account_id: str,
        status: str,
        health_data: Optional[Dict[str, Any]] = None
    ):
        """Send account status update"""
        message = {
            "type": MessageType.ACCOUNT_STATUS.value,
            "account_id": account_id,
            "status": status,
            "health_data": health_data or {},
            "message": f"Account {account_id} status: {status}"
        }

        await self.send_personal_message(user_id, message)
        await self._publish_to_redis(f"user:{user_id}:account_status", message)

    async def handle_client_message(
        self,
        websocket: WebSocket,
        user_id: str,
        connection_id: str,
        message: Dict[str, Any]
    ):
        """Handle incoming message from client"""
        message_type = message.get("type")

        if message_type == MessageType.PING.value:
            # Update last ping time
            if connection_id in self.connection_metadata:
                self.connection_metadata[connection_id]["last_ping"] = datetime.utcnow().isoformat()

            # Send pong response
            await websocket.send_text(json.dumps({
                "type": MessageType.PONG.value,
                "server_time": datetime.utcnow().isoformat()
            }))

        elif message_type == "subscribe":
            # Update subscription filters
            filters = message.get("filters", {})
            if connection_id in self.connection_metadata:
                self.connection_metadata[connection_id]["filters"] = filters

            await websocket.send_text(json.dumps({
                "type": "subscription_updated",
                "filters": filters,
                "message": "Subscription filters updated"
            }))

        elif message_type == "get_stats":
            # Send connection stats
            stats = {
                "type": "stats",
                "connected_since": self.connection_metadata.get(connection_id, {}).get("connected_at"),
                "total_user_connections": len(self.user_connections.get(user_id, set())),
                "server_time": datetime.utcnow().isoformat()
            }
            await websocket.send_text(json.dumps(stats))

    def _message_matches_filters(
        self,
        message: Dict[str, Any],
        user_id: str,
        websocket: WebSocket
    ) -> bool:
        """Check if message matches user's subscription filters"""
        # Find connection metadata for this websocket
        connection_filters = {}
        for conn_id, metadata in self.connection_metadata.items():
            if metadata.get("websocket") is websocket and metadata.get("user_id") == user_id:
                connection_filters = metadata.get("filters", {})
                break

        if not connection_filters:
            return True  # No filters means accept all

        # Apply filters
        if "message_types" in connection_filters:
            if message.get("type") not in connection_filters["message_types"]:
                return False

        if "account_ids" in connection_filters:
            if message.get("account_id") not in connection_filters["account_ids"]:
                return False

        return True

    async def _publish_to_redis(self, channel: str, message: Dict[str, Any]):
        """Publish message to Redis for other instances"""
        if not self.redis_client:
            return

        try:
            await self.redis_client.publish(channel, json.dumps(message))
        except Exception as e:
            logger.error("Failed to publish to Redis", channel=channel, error=str(e))

    async def _subscribe_to_redis_channels(self, user_id: str):
        """Subscribe to Redis channels for this user"""
        if not self.redis_client:
            return

        try:
            pubsub = self.redis_client.pubsub()
            channels = [
                f"user:{user_id}:cost_updates",
                f"user:{user_id}:waste_detection",
                f"user:{user_id}:recommendations",
                f"user:{user_id}:job_status",
                f"user:{user_id}:account_status"
            ]

            await pubsub.subscribe(*channels)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self.send_personal_message(user_id, data)
                    except Exception as e:
                        logger.error("Error processing Redis message", error=str(e))

        except Exception as e:
            logger.error("Redis subscription error", user_id=user_id, error=str(e))

    async def cleanup_stale_connections(self):
        """Clean up connections that haven't pinged recently"""
        current_time = datetime.utcnow()
        stale_threshold = 300  # 5 minutes

        stale_connections = []
        for connection_id, metadata in self.connection_metadata.items():
            try:
                last_ping_str = metadata.get("last_ping")
                if last_ping_str:
                    last_ping = datetime.fromisoformat(last_ping_str)
                    if (current_time - last_ping).total_seconds() > stale_threshold:
                        stale_connections.append((
                            metadata.get("user_id"),
                            connection_id
                        ))
            except Exception:
                stale_connections.append((
                    metadata.get("user_id"),
                    connection_id
                ))

        # Clean up stale connections
        for user_id, connection_id in stale_connections:
            if user_id and connection_id:
                await self.disconnect(user_id, connection_id)

        if stale_connections:
            logger.info("Cleaned up stale WebSocket connections",
                       count=len(stale_connections))

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get WebSocket connection statistics"""
        return {
            "total_connections": len(self.connection_metadata),
            "unique_users": len(self.user_connections),
            "connections_per_user": {
                user_id: len(connections)
                for user_id, connections in self.user_connections.items()
            }
        }


# Global WebSocket manager instance
websocket_manager = WebSocketManager()