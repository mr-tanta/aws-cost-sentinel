import json
import uuid
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from jose import jwt, JWTError
import structlog

from app.core.config import settings
from app.core.security import create_api_response
from app.services.websocket_service import websocket_manager, MessageType

router = APIRouter()
logger = structlog.get_logger(__name__)
security = HTTPBearer()


async def get_user_from_websocket_token(token: str) -> Optional[str]:
    """Extract user ID from WebSocket token"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "access":
            return None

        return user_id
    except JWTError:
        return None


@router.websocket("/connect")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    filters: Optional[str] = Query(None, description="JSON-encoded subscription filters")
):
    """Main WebSocket endpoint for real-time updates"""

    # Authenticate user
    user_id = await get_user_from_websocket_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Parse filters
    subscription_filters = {}
    if filters:
        try:
            subscription_filters = json.loads(filters)
        except json.JSONDecodeError:
            await websocket.close(code=4002, reason="Invalid filters format")
            return

    # Generate connection ID
    connection_id = str(uuid.uuid4())

    try:
        # Connect user
        await websocket_manager.connect(
            websocket=websocket,
            user_id=user_id,
            connection_id=connection_id,
            filters=subscription_filters
        )

        logger.info("WebSocket connection established",
                   user_id=user_id,
                   connection_id=connection_id)

        # Handle messages from client
        while True:
            try:
                # Receive message from client
                message_text = await websocket.receive_text()
                message = json.loads(message_text)

                # Handle the message
                await websocket_manager.handle_client_message(
                    websocket=websocket,
                    user_id=user_id,
                    connection_id=connection_id,
                    message=message
                )

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                # Send error for invalid JSON
                await websocket.send_text(json.dumps({
                    "type": MessageType.ERROR.value,
                    "message": "Invalid JSON format"
                }))
            except Exception as e:
                logger.error("Error handling WebSocket message",
                           user_id=user_id,
                           connection_id=connection_id,
                           error=str(e))
                await websocket.send_text(json.dumps({
                    "type": MessageType.ERROR.value,
                    "message": "Internal server error"
                }))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected",
                   user_id=user_id,
                   connection_id=connection_id)
    except Exception as e:
        logger.error("WebSocket connection error",
                    user_id=user_id,
                    connection_id=connection_id,
                    error=str(e))
    finally:
        # Cleanup connection
        await websocket_manager.disconnect(user_id, connection_id)


@router.get("/stats", response_model=dict)
async def get_websocket_stats():
    """Get WebSocket connection statistics"""
    try:
        stats = websocket_manager.get_connection_stats()
        return create_api_response(
            success=True,
            data=stats
        )
    except Exception as e:
        logger.error("Failed to get WebSocket stats", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve WebSocket statistics"
        )


@router.post("/broadcast", response_model=dict)
async def broadcast_message(
    message: dict,
    user_filter: Optional[str] = Query(None, description="Optional user filter function")
):
    """Broadcast message to all connected users (admin only)"""
    try:
        # In production, add proper admin authentication here

        await websocket_manager.broadcast_message(message)

        return create_api_response(
            success=True,
            message="Message broadcasted successfully"
        )
    except Exception as e:
        logger.error("Failed to broadcast message", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast message"
        )


# Notification endpoints for triggering real-time updates

@router.post("/notify/cost-update", response_model=dict)
async def notify_cost_update(
    user_id: str,
    account_id: str,
    cost_data: dict
):
    """Trigger cost update notification"""
    try:
        await websocket_manager.send_cost_update(
            user_id=user_id,
            account_id=account_id,
            cost_data=cost_data
        )

        return create_api_response(
            success=True,
            message="Cost update notification sent"
        )
    except Exception as e:
        logger.error("Failed to send cost update notification", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send cost update notification"
        )


@router.post("/notify/waste-detected", response_model=dict)
async def notify_waste_detected(
    user_id: str,
    account_id: str,
    waste_items: list
):
    """Trigger waste detection notification"""
    try:
        await websocket_manager.send_waste_detection(
            user_id=user_id,
            account_id=account_id,
            waste_items=waste_items
        )

        return create_api_response(
            success=True,
            message="Waste detection notification sent"
        )
    except Exception as e:
        logger.error("Failed to send waste detection notification", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send waste detection notification"
        )


@router.post("/notify/recommendation-ready", response_model=dict)
async def notify_recommendation_ready(
    user_id: str,
    account_id: str,
    recommendations: list
):
    """Trigger recommendation ready notification"""
    try:
        await websocket_manager.send_recommendation_update(
            user_id=user_id,
            account_id=account_id,
            recommendations=recommendations
        )

        return create_api_response(
            success=True,
            message="Recommendation notification sent"
        )
    except Exception as e:
        logger.error("Failed to send recommendation notification", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send recommendation notification"
        )


@router.post("/notify/job-status", response_model=dict)
async def notify_job_status_update(
    user_id: str,
    job_id: str,
    status: str,
    progress: Optional[dict] = None
):
    """Trigger job status update notification"""
    try:
        await websocket_manager.send_job_status_update(
            user_id=user_id,
            job_id=job_id,
            status=status,
            progress=progress
        )

        return create_api_response(
            success=True,
            message="Job status notification sent"
        )
    except Exception as e:
        logger.error("Failed to send job status notification", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send job status notification"
        )


@router.post("/notify/account-status", response_model=dict)
async def notify_account_status_update(
    user_id: str,
    account_id: str,
    status: str,
    health_data: Optional[dict] = None
):
    """Trigger account status update notification"""
    try:
        await websocket_manager.send_account_status_update(
            user_id=user_id,
            account_id=account_id,
            status=status,
            health_data=health_data
        )

        return create_api_response(
            success=True,
            message="Account status notification sent"
        )
    except Exception as e:
        logger.error("Failed to send account status notification", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send account status notification"
        )