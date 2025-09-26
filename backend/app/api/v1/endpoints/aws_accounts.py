from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import structlog

from app.core.security import get_current_user_id, create_api_response
from app.db.base import get_database
from app.models.aws_account import AWSAccount, AWSAccountStatus
from app.schemas.aws_account import (
    AWSAccountCreate,
    AWSAccountUpdate,
    AWSAccountResponse
)
from app.services.aws_client import aws_client_manager

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/", response_model=dict)
async def get_aws_accounts(
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get all AWS accounts for the current user"""
    try:
        result = await db.execute(
            select(AWSAccount).where(AWSAccount.is_active == True).order_by(AWSAccount.name)
        )
        accounts = result.scalars().all()

        return create_api_response(
            success=True,
            data=[AWSAccountResponse.from_orm(account) for account in accounts]
        )

    except Exception as e:
        logger.error("Failed to get AWS accounts", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve AWS accounts"
        )


@router.post("/", response_model=dict)
async def create_aws_account(
    account_data: AWSAccountCreate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Create a new AWS account"""
    try:
        # Check if account with same account_id already exists
        existing_result = await db.execute(
            select(AWSAccount).where(AWSAccount.account_id == account_data.account_id)
        )
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS account with this ID already exists"
            )

        # Create new AWS account record
        db_account = AWSAccount(
            name=account_data.name,
            account_id=account_data.account_id,
            region=account_data.region,
            role_arn=account_data.role_arn,
            external_id=account_data.external_id,
            status=AWSAccountStatus.PENDING
        )

        db.add(db_account)
        await db.commit()
        await db.refresh(db_account)

        logger.info("AWS account created", account_id=db_account.account_id, name=db_account.name)

        return create_api_response(
            success=True,
            data=AWSAccountResponse.from_orm(db_account),
            message="AWS account created successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create AWS account", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create AWS account"
        )


@router.get("/{account_id}", response_model=dict)
async def get_aws_account(
    account_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get a specific AWS account"""
    try:
        result = await db.execute(
            select(AWSAccount).where(AWSAccount.id == account_id, AWSAccount.is_active == True)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not found"
            )

        return create_api_response(
            success=True,
            data=AWSAccountResponse.from_orm(account)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get AWS account", account_id=str(account_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve AWS account"
        )


@router.put("/{account_id}", response_model=dict)
async def update_aws_account(
    account_id: UUID,
    account_update: AWSAccountUpdate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Update an AWS account"""
    try:
        result = await db.execute(
            select(AWSAccount).where(AWSAccount.id == account_id, AWSAccount.is_active == True)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not found"
            )

        # Update fields
        if account_update.name is not None:
            account.name = account_update.name
        if account_update.region is not None:
            account.region = account_update.region
        if account_update.role_arn is not None:
            account.role_arn = account_update.role_arn
        if account_update.external_id is not None:
            account.external_id = account_update.external_id
        if account_update.is_active is not None:
            account.is_active = account_update.is_active

        await db.commit()
        await db.refresh(account)

        # Clear cached sessions for this account
        aws_client_manager.clear_cache(account.account_id)

        logger.info("AWS account updated", account_id=account.account_id)

        return create_api_response(
            success=True,
            data=AWSAccountResponse.from_orm(account),
            message="AWS account updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update AWS account", account_id=str(account_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update AWS account"
        )


@router.delete("/{account_id}", response_model=dict)
async def delete_aws_account(
    account_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Delete an AWS account (soft delete)"""
    try:
        result = await db.execute(
            select(AWSAccount).where(AWSAccount.id == account_id, AWSAccount.is_active == True)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not found"
            )

        # Soft delete
        account.is_active = False
        await db.commit()

        # Clear cached sessions
        aws_client_manager.clear_cache(account.account_id)

        logger.info("AWS account deleted", account_id=account.account_id)

        return create_api_response(
            success=True,
            message="AWS account deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete AWS account", account_id=str(account_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete AWS account"
        )


@router.post("/{account_id}/test", response_model=dict)
async def test_aws_connection(
    account_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Test AWS connection for an account"""
    try:
        result = await db.execute(
            select(AWSAccount).where(AWSAccount.id == account_id, AWSAccount.is_active == True)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not found"
            )

        # Test the connection
        connection_result = await aws_client_manager.test_connection(account)

        # Update account status based on test result
        if connection_result['status'] == 'success':
            account.status = AWSAccountStatus.CONNECTED
            account.error_message = None
        else:
            account.status = AWSAccountStatus.ERROR
            account.error_message = connection_result.get('error_message')

        await db.commit()

        logger.info("AWS connection tested",
                   account_id=account.account_id,
                   status=connection_result['status'])

        return create_api_response(
            success=connection_result['status'] == 'success',
            data=connection_result,
            message="Connection test completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to test AWS connection", account_id=str(account_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test AWS connection"
        )


@router.post("/{account_id}/sync", response_model=dict)
async def sync_aws_account(
    account_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Trigger manual sync for an AWS account"""
    try:
        result = await db.execute(
            select(AWSAccount).where(AWSAccount.id == account_id, AWSAccount.is_active == True)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not found"
            )

        if account.status != AWSAccountStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account must be connected before syncing"
            )

        # Update status to syncing
        account.status = AWSAccountStatus.SYNCING
        await db.commit()

        # TODO: Trigger background sync job
        # from app.tasks.sync_tasks import sync_account_data
        # sync_account_data.delay(str(account.id))

        logger.info("AWS account sync triggered", account_id=account.account_id)

        return create_api_response(
            success=True,
            message="Account sync started"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to sync AWS account", account_id=str(account_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync AWS account"
        )