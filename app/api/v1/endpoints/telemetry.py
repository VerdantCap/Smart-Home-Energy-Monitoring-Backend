from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from app.core.database import get_db
from app.core.deps import (
    get_current_active_user, 
    get_current_admin_user,
    telemetry_rate_limiter,
    general_rate_limiter,
    AuthUser
)
from app.schemas.telemetry import (
    TelemetryCreate, 
    TelemetryResponse, 
    TelemetryBatch,
    TelemetryQuery,
    TelemetryStats,
    EnergyConsumptionSummary,
    RealTimeMetrics,
    HealthMetrics
)
from app.services.telemetry_service import get_telemetry_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=TelemetryResponse, status_code=status.HTTP_201_CREATED)
async def create_telemetry(
    request: Request,
    telemetry_data: TelemetryCreate,
    current_user: AuthUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(telemetry_rate_limiter)
):
    """Create a single telemetry record"""
    try:
        telemetry_service = get_telemetry_service(db)
        
        telemetry = await telemetry_service.create_telemetry(telemetry_data, current_user)
        if not telemetry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create telemetry record"
            )
        
        logger.info(f"Telemetry created for device {telemetry_data.device_id} by user {current_user.email}")
        return TelemetryResponse.model_validate(telemetry)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Telemetry creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create telemetry record"
        )


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def create_telemetry_batch(
    request: Request,
    batch_data: TelemetryBatch,
    current_user: AuthUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(telemetry_rate_limiter)
):
    """Create multiple telemetry records in batch"""
    try:
        telemetry_service = get_telemetry_service(db)
        
        result = await telemetry_service.create_telemetry_batch(batch_data.telemetry_data, current_user)
        
        logger.info(f"Batch telemetry created: {result['created']} success, {result['failed']} failed by user {current_user.email}")
        return {
            "message": "Batch telemetry processing completed",
            "created": result["created"],
            "failed": result["failed"],
            "total": result["total"]
        }
        
    except Exception as e:
        logger.error(f"Batch telemetry creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process batch telemetry"
        )


@router.get("/", response_model=List[TelemetryResponse])
async def get_telemetry(
    device_ids: Optional[List[str]] = Query(None, description="Filter by device IDs"),
    start_time: Optional[datetime] = Query(None, description="Start time for data range"),
    end_time: Optional[datetime] = Query(None, description="End time for data range"),
    limit: int = Query(100, ge=1, le=10000, description="Maximum number of records"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_user: AuthUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(general_rate_limiter)
):
    """Get telemetry data with filtering and pagination"""
    try:
        telemetry_service = get_telemetry_service(db)
        
        query = TelemetryQuery(
            device_ids=device_ids,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        telemetry_data = await telemetry_service.get_telemetry(query, current_user)
        
        return [TelemetryResponse.model_validate(t) for t in telemetry_data]
        
    except Exception as e:
        logger.error(f"Get telemetry error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve telemetry data"
        )


@router.get("/stats/{device_id}", response_model=TelemetryStats)
async def get_device_stats(
    device_id: str,
    start_time: datetime = Query(..., description="Start time for statistics"),
    end_time: datetime = Query(..., description="End time for statistics"),
    current_user: AuthUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(general_rate_limiter)
):
    """Get telemetry statistics for a specific device"""
    try:
        telemetry_service = get_telemetry_service(db)
        
        stats = await telemetry_service.get_telemetry_stats(device_id, start_time, end_time, current_user)
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No telemetry data found for the specified device and time range"
            )
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get device stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve device statistics"
        )


@router.get("/summary", response_model=EnergyConsumptionSummary)
async def get_energy_summary(
    start_time: datetime = Query(..., description="Start time for summary"),
    end_time: datetime = Query(..., description="End time for summary"),
    current_user: AuthUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(general_rate_limiter)
):
    """Get energy consumption summary for all user devices"""
    try:
        telemetry_service = get_telemetry_service(db)
        
        summary = await telemetry_service.get_energy_consumption_summary(start_time, end_time, current_user)
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No energy consumption data found for the specified time range"
            )
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get energy summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve energy consumption summary"
        )


@router.get("/realtime", response_model=RealTimeMetrics)
async def get_realtime_metrics(
    current_user: AuthUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(general_rate_limiter)
):
    """Get real-time metrics for user devices"""
    try:
        telemetry_service = get_telemetry_service(db)
        
        metrics = await telemetry_service.get_real_time_metrics(current_user)
        if not metrics:
            # Return empty metrics if no data
            metrics = RealTimeMetrics(
                timestamp=datetime.utcnow(),
                active_devices=0,
                total_current_power=0.0,
                average_power_per_device=0.0,
                highest_consuming_device=None,
                highest_consumption=None
            )
        
        logger.info(f"Real-time metrics result: timestamp={metrics.timestamp} "
                   f"active_devices={metrics.active_devices} "
                   f"total_current_power={metrics.total_current_power} "
                   f"average_power_per_device={metrics.average_power_per_device} "
                   f"highest_consuming_device={metrics.highest_consuming_device} "
                   f"highest_consumption={metrics.highest_consumption}")
        
        return metrics
        
    except Exception as e:
        logger.error(f"Get realtime metrics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve real-time metrics"
        )


@router.get("/health", response_model=HealthMetrics)
async def get_health_metrics(
    current_user: AuthUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get service health metrics (admin only)"""
    try:
        from app.models.device import Device
        from app.models.telemetry import Telemetry
        from sqlalchemy import func, select
        
        # Get database status
        try:
            await db.execute(select(1))
            database_status = "healthy"
        except Exception:
            database_status = "unhealthy"
        
        # Get Redis status
        from app.core.redis_client import redis_service
        try:
            await redis_service.get("health_check")
            redis_status = "healthy"
        except Exception:
            redis_status = "unhealthy"
        
        # Get total devices
        device_count_stmt = select(func.count(Device.id))
        device_result = await db.execute(device_count_stmt)
        total_devices = device_result.scalar() or 0
        
        # Get total telemetry records
        telemetry_count_stmt = select(func.count(Telemetry.id))
        telemetry_result = await db.execute(telemetry_count_stmt)
        total_telemetry = telemetry_result.scalar() or 0
        
        # Get last telemetry timestamp
        last_telemetry_stmt = select(func.max(Telemetry.timestamp))
        last_result = await db.execute(last_telemetry_stmt)
        last_timestamp = last_result.scalar()
        
        return HealthMetrics(
            service="telemetry-service",
            status="healthy" if database_status == "healthy" and redis_status == "healthy" else "degraded",
            timestamp=datetime.utcnow(),
            database_status=database_status,
            redis_status=redis_status,
            total_devices=total_devices,
            total_telemetry_records=total_telemetry,
            last_telemetry_timestamp=last_timestamp,
            avg_requests_per_minute=0.0  # Could be implemented with request tracking
        )
        
    except Exception as e:
        logger.error(f"Get health metrics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve health metrics"
        )


# Device management endpoints
@router.get("/devices", response_model=List[dict])
async def get_user_devices(
    current_user: AuthUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(general_rate_limiter)
):
    """Get all devices for the current user"""
    try:
        from app.models.device import Device
        from sqlalchemy import select
        
        stmt = select(Device).where(Device.user_id == current_user.id)
        result = await db.execute(stmt)
        devices = result.scalars().all()
        
        return [device.to_dict() for device in devices]
        
    except Exception as e:
        logger.error(f"Get user devices error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user devices"
        )


@router.get("/devices/{device_id}/latest")
async def get_device_latest_telemetry(
    device_id: str,
    current_user: AuthUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(general_rate_limiter)
):
    """Get latest telemetry data for a specific device"""
    try:
        from app.models.telemetry import Telemetry
        from sqlalchemy import select, desc, and_
        
        stmt = select(Telemetry).where(
            and_(
                Telemetry.user_id == current_user.id,
                Telemetry.device_id == device_id
            )
        ).order_by(desc(Telemetry.timestamp)).limit(1)
        
        result = await db.execute(stmt)
        latest_telemetry = result.scalar_one_or_none()
        
        if not latest_telemetry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No telemetry data found for this device"
            )
        
        return TelemetryResponse.model_validate(latest_telemetry)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get device latest telemetry error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve latest telemetry data"
        )
