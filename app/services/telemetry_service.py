from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, text
from sqlalchemy.exc import IntegrityError
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging
import json
import uuid

from app.models.telemetry import Telemetry, TelemetryHourlyAggregate
from app.models.device import Device
from app.schemas.telemetry import (
    TelemetryCreate, TelemetryQuery, TelemetryStats, 
    TelemetryAggregateResponse, EnergyConsumptionSummary,
    DeviceEnergyTrend, RealTimeMetrics
)
from app.core.deps import AuthUser
from app.core.redis_client import redis_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class TelemetryService:
    """Service layer for telemetry operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_telemetry(self, telemetry_data: TelemetryCreate, user: AuthUser) -> Optional[Telemetry]:
        """Create a single telemetry record"""
        try:
            # Ensure device exists and user has access
            device = await self._get_or_create_device(telemetry_data.device_id, user)
            if not device:
                return None
            
            # Create telemetry record
            db_telemetry = Telemetry(
                device_id=telemetry_data.device_id,
                user_id=user.id,
                timestamp=telemetry_data.timestamp,
                energy_watts=telemetry_data.energy_watts
            )
            
            self.db.add(db_telemetry)
            await self.db.commit()
            await self.db.refresh(db_telemetry)
            
            # Update real-time metrics in Redis
            await self._update_realtime_metrics(telemetry_data.device_id, telemetry_data.energy_watts)
            
            logger.info(f"Telemetry created for device {telemetry_data.device_id}")
            return db_telemetry
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create telemetry: {e}")
            return None
    
    async def create_telemetry_batch(self, telemetry_list: List[TelemetryCreate], user: AuthUser) -> Dict[str, Any]:
        """Create multiple telemetry records in batch"""
        try:
            created_count = 0
            failed_count = 0
            
            for telemetry_data in telemetry_list:
                # Ensure device exists and user has access
                device = await self._get_or_create_device(telemetry_data.device_id, user)
                if not device:
                    failed_count += 1
                    continue
                
                # Create telemetry record
                db_telemetry = Telemetry(
                    device_id=telemetry_data.device_id,
                    user_id=user.id,
                    timestamp=telemetry_data.timestamp,
                    energy_watts=telemetry_data.energy_watts
                )
                
                self.db.add(db_telemetry)
                created_count += 1
            
            await self.db.commit()
            
            logger.info(f"Batch telemetry created: {created_count} success, {failed_count} failed")
            return {
                "created": created_count,
                "failed": failed_count,
                "total": len(telemetry_list)
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create batch telemetry: {e}")
            return {"created": 0, "failed": len(telemetry_list), "total": len(telemetry_list)}
    
    async def get_telemetry(self, query: TelemetryQuery, user: AuthUser) -> List[Telemetry]:
        """Get telemetry data with filtering"""
        try:
            stmt = select(Telemetry).where(Telemetry.user_id == user.id)
            
            # Apply filters
            if query.device_ids:
                stmt = stmt.where(Telemetry.device_id.in_(query.device_ids))
            
            if query.start_time:
                stmt = stmt.where(Telemetry.timestamp >= query.start_time)
            
            if query.end_time:
                stmt = stmt.where(Telemetry.timestamp <= query.end_time)
            
            # Order by timestamp descending
            stmt = stmt.order_by(desc(Telemetry.timestamp))
            
            # Apply pagination
            stmt = stmt.offset(query.offset).limit(query.limit)
            
            result = await self.db.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get telemetry: {e}")
            return []
    
    async def get_telemetry_stats(self, device_id: str, start_time: datetime, end_time: datetime, user: AuthUser) -> Optional[TelemetryStats]:
        """Get telemetry statistics for a device"""
        try:
            # Check cache first
            cache_key = f"telemetry_stats:{user.id}:{device_id}:{start_time.isoformat()}:{end_time.isoformat()}"
            cached_stats = await redis_service.get(cache_key)
            
            if cached_stats:
                return TelemetryStats.model_validate_json(cached_stats)
            
            # Query database
            stmt = select(
                func.avg(Telemetry.energy_watts).label('avg_energy_watts'),
                func.min(Telemetry.energy_watts).label('min_energy_watts'),
                func.max(Telemetry.energy_watts).label('max_energy_watts'),
                func.count(Telemetry.id).label('sample_count'),
                func.sum(Telemetry.energy_watts).label('total_energy_wh')  # Values are already scaled for 30-second intervals in simulation
            ).where(
                and_(
                    Telemetry.user_id == user.id,
                    Telemetry.device_id == device_id,
                    Telemetry.timestamp >= start_time,
                    Telemetry.timestamp <= end_time
                )
            )
            
            result = await self.db.execute(stmt)
            row = result.first()
            
            if not row or row.sample_count == 0:
                return None
            
            # Get device name
            device_stmt = select(Device.name).where(
                and_(Device.device_id == device_id, Device.user_id == user.id)
            )
            device_result = await self.db.execute(device_stmt)
            device_name = device_result.scalar_one_or_none()
            
            stats = TelemetryStats(
                device_id=device_id,
                device_name=device_name,
                total_energy_wh=float(row.total_energy_wh or 0),
                avg_energy_watts=float(row.avg_energy_watts or 0),
                max_energy_watts=float(row.max_energy_watts or 0),
                min_energy_watts=float(row.min_energy_watts or 0),
                sample_count=int(row.sample_count or 0),
                start_time=start_time,
                end_time=end_time
            )
            
            # Cache the result
            await redis_service.set(cache_key, stats.model_dump_json(), expire=settings.CACHE_TTL_SECONDS)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get telemetry stats: {e}")
            return None
    
    async def get_energy_consumption_summary(self, start_time: datetime, end_time: datetime, user: AuthUser) -> Optional[EnergyConsumptionSummary]:
        """Get energy consumption summary for all user devices"""
        try:
            # Get all user devices
            devices_stmt = select(Device).where(Device.user_id == user.id)
            devices_result = await self.db.execute(devices_stmt)
            devices = devices_result.scalars().all()
            
            if not devices:
                return None
            
            device_ids = [device.device_id for device in devices]
            
            # Get overall statistics
            overall_stmt = select(
                func.avg(Telemetry.energy_watts).label('avg_energy_watts'),
                func.max(Telemetry.energy_watts).label('peak_energy_watts'),
                func.sum(Telemetry.energy_watts).label('total_energy_wh')  # Values are already scaled for 30-second intervals in simulation
            ).where(
                and_(
                    Telemetry.user_id == user.id,
                    Telemetry.device_id.in_(device_ids),
                    Telemetry.timestamp >= start_time,
                    Telemetry.timestamp <= end_time
                )
            )
            
            overall_result = await self.db.execute(overall_stmt)
            overall_row = overall_result.first()
            
            # Get peak timestamp
            peak_stmt = select(Telemetry.timestamp).where(
                and_(
                    Telemetry.user_id == user.id,
                    Telemetry.device_id.in_(device_ids),
                    Telemetry.timestamp >= start_time,
                    Telemetry.timestamp <= end_time,
                    Telemetry.energy_watts == overall_row.peak_energy_watts
                )
            ).limit(1)
            
            peak_result = await self.db.execute(peak_stmt)
            peak_timestamp = peak_result.scalar_one_or_none()
            
            # Get top consumers
            top_consumers = []
            for device in devices[:5]:  # Top 5 consumers
                stats = await self.get_telemetry_stats(device.device_id, start_time, end_time, user)
                if stats:
                    top_consumers.append(stats)
            
            # Sort by total energy consumption
            top_consumers.sort(key=lambda x: x.total_energy_wh, reverse=True)
            
            return EnergyConsumptionSummary(
                total_devices=len(devices),
                total_energy_wh=float(overall_row.total_energy_wh or 0),
                avg_energy_watts=float(overall_row.avg_energy_watts or 0),
                peak_energy_watts=float(overall_row.peak_energy_watts or 0),
                peak_timestamp=peak_timestamp,
                period_start=start_time,
                period_end=end_time,
                top_consumers=top_consumers[:5]
            )
            
        except Exception as e:
            logger.error(f"Failed to get energy consumption summary: {e}")
            return None
    
    async def get_real_time_metrics(self, user: AuthUser) -> Optional[RealTimeMetrics]:
        """Get real-time metrics for user devices"""
        try:
            # Get from Redis cache
            cache_key = f"realtime_metrics:{user.id}"
            cached_metrics = await redis_service.get(cache_key)
            
            if cached_metrics:
                try:
                    logger.info(f"Returning cached real-time metrics for user {user.id}")
                    return RealTimeMetrics.model_validate_json(cached_metrics)
                except Exception as cache_error:
                    logger.warning(f"Failed to validate cached metrics for user {user.id}: {cache_error}")
                    # Clear invalid cache and continue to recalculate
                    await redis_service.delete(cache_key)
            
            # Calculate from recent data (last 5 minutes)
            recent_time = datetime.utcnow() - timedelta(minutes=5)
            
                        # Get the latest reading per device (this is the correct approach)
            latest_per_device_stmt = select(
                Telemetry.device_id,
                func.max(Telemetry.timestamp).label('latest_timestamp')
            ).where(
                and_(
                    Telemetry.user_id == user.id,
                    Telemetry.timestamp >= recent_time
                )
            ).group_by(Telemetry.device_id)
            
            latest_result = await self.db.execute(latest_per_device_stmt)
            latest_devices = latest_result.all()
            
            if not latest_devices:
                logger.warning(f"No recent telemetry data found for user {user.id}")
                return RealTimeMetrics(
                    timestamp=datetime.utcnow(),
                    active_devices=0,
                    total_current_power=0.0,
                    average_power_per_device=0.0,
                    highest_consuming_device=None,
                    highest_consumption=None
                )
            
            # Get the actual power values for the latest readings
            device_powers = []
            total_power = 0.0
            max_power = 0.0
            max_device = None
            
            for device_row in latest_devices:
                power_stmt = select(Telemetry.energy_watts).where(
                    and_(
                        Telemetry.user_id == user.id,
                        Telemetry.device_id == device_row.device_id,
                        Telemetry.timestamp == device_row.latest_timestamp
                    )
                ).limit(1)
                
                power_result = await self.db.execute(power_stmt)
                power_value = power_result.scalar_one_or_none()
                
                if power_value is not None:
                    try:
                        # Convert Decimal to float to avoid type errors
                        power_float = float(power_value)
                        # Validate power value is reasonable (adjusted for 30-second scaled values)
                        if 0 <= power_float <= 50000:  # 0-50kW range (includes small scaled values)
                            device_powers.append(power_float)
                            total_power += power_float
                            
                            if power_float > max_power:
                                max_power = power_float
                                max_device = device_row.device_id
                            
                            logger.debug(f"Device {device_row.device_id}: {power_float}W")
                        else:
                            logger.warning(f"Invalid power value {power_float}W for device {device_row.device_id}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to convert power value for device {device_row.device_id}: {e}")
            
            active_devices = len(device_powers)
            avg_power = total_power / active_devices if active_devices > 0 else 0.0
            
            metrics = RealTimeMetrics(
                timestamp=datetime.utcnow(),
                active_devices=active_devices,
                total_current_power=total_power,
                average_power_per_device=avg_power,
                highest_consuming_device=max_device,
                highest_consumption=max_power if max_power > 0 else None
            )
            
            logger.info(f"Calculated real-time metrics for user {user.id}: "
                       f"active_devices={active_devices}, total_power={total_power:.1f}W, "
                       f"avg_power={avg_power:.1f}W, max_device={max_device}")
            
            # Cache for 30 seconds
            await redis_service.set(cache_key, metrics.model_dump_json(), expire=30)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get real-time metrics for user {user.id}: {e}")
            return RealTimeMetrics(
                timestamp=datetime.utcnow(),
                active_devices=0,
                total_current_power=0.0,
                average_power_per_device=0.0,
                highest_consuming_device=None,
                highest_consumption=None
            )
    
    async def _get_or_create_device(self, device_id: str, user: AuthUser) -> Optional[Device]:
        """Get existing device or create new one"""
        try:
            # Check if device exists
            stmt = select(Device).where(
                and_(Device.device_id == device_id, Device.user_id == user.id)
            )
            result = await self.db.execute(stmt)
            device = result.scalar_one_or_none()
            
            if device:
                return device
            
            # Create new device
            new_device = Device(
                user_id=user.id,
                device_id=device_id,
                name=f"Device {device_id}",
                type="unknown",
                location="unknown"
            )
            
            self.db.add(new_device)
            await self.db.commit()
            await self.db.refresh(new_device)
            
            logger.info(f"Created new device: {device_id} for user {user.id}")
            return new_device
            
        except Exception as e:
            logger.error(f"Failed to get or create device: {e}")
            return None
    
    async def _update_realtime_metrics(self, device_id: str, energy_watts: float) -> None:
        """Update real-time metrics in Redis"""
        try:
            # Update device current power
            device_key = f"device_power:{device_id}"
            await redis_service.set(device_key, str(energy_watts), expire=300)  # 5 minutes
            
            # Update last activity
            activity_key = f"device_activity:{device_id}"
            await redis_service.set(activity_key, datetime.utcnow().isoformat(), expire=300)
            
        except Exception as e:
            logger.error(f"Failed to update real-time metrics: {e}")
    
    async def clear_realtime_metrics_cache(self, user: AuthUser) -> None:
        """Clear real-time metrics cache for a user"""
        try:
            cache_key = f"realtime_metrics:{user.id}"
            await redis_service.delete(cache_key)
            logger.info(f"Cleared real-time metrics cache for user {user.id}")
        except Exception as e:
            logger.error(f"Failed to clear real-time metrics cache: {e}")
    
    async def validate_metrics_consistency(self, user: AuthUser) -> Dict[str, Any]:
        """Validate consistency between real-time metrics and energy consumption data"""
        try:
            # Get real-time metrics
            realtime = await self.get_real_time_metrics(user)
            
            # Get recent energy consumption (last hour for comparison)
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
            energy_summary = await self.get_energy_consumption_summary(start_time, end_time, user)
            
            if not realtime or not energy_summary:
                return {"status": "insufficient_data", "message": "Not enough data for validation"}
            
            validation_results = {
                "timestamp": datetime.utcnow(),
                "realtime_data": {
                    "active_devices": realtime.active_devices,
                    "total_current_power": realtime.total_current_power,
                    "average_power_per_device": realtime.average_power_per_device,
                    "highest_consumption": realtime.highest_consumption
                },
                "energy_data": {
                    "total_devices": energy_summary.total_devices,
                    "avg_energy_watts": energy_summary.avg_energy_watts,
                    "peak_energy_watts": energy_summary.peak_energy_watts,
                    "total_energy_wh": energy_summary.total_energy_wh
                },
                "consistency_checks": {}
            }
            
            # Check 1: Active devices should not exceed total devices
            validation_results["consistency_checks"]["device_count_valid"] = (
                realtime.active_devices <= energy_summary.total_devices
            )
            
            # Check 2: Current highest consumption should be reasonable compared to historical peak
            if realtime.highest_consumption and energy_summary.peak_energy_watts:
                peak_ratio = realtime.highest_consumption / energy_summary.peak_energy_watts
                validation_results["consistency_checks"]["peak_power_reasonable"] = (
                    0.1 <= peak_ratio <= 2.0  # Current should be within 10%-200% of historical peak
                )
                validation_results["consistency_checks"]["peak_power_ratio"] = peak_ratio
            
            # Check 3: Average power relationship (allowing for variation)
            if realtime.active_devices > 0 and energy_summary.avg_energy_watts > 0:
                expected_total = energy_summary.avg_energy_watts * realtime.active_devices
                actual_total = realtime.total_current_power
                if expected_total > 0:
                    power_ratio = actual_total / expected_total
                    validation_results["consistency_checks"]["power_average_reasonable"] = (
                        0.2 <= power_ratio <= 5.0  # Allow significant variation due to time differences
                    )
                    validation_results["consistency_checks"]["power_ratio"] = power_ratio
            
            # Check 4: Energy accumulation makes sense
            if energy_summary.total_energy_wh > 0 and energy_summary.avg_energy_watts > 0:
                # For 1 hour period with 30-second intervals: expected ~120 samples
                expected_samples = 120  # 1 hour = 120 thirty-second intervals
                expected_energy = energy_summary.avg_energy_watts * expected_samples  # Values already scaled in simulation
                actual_energy = energy_summary.total_energy_wh
                if expected_energy > 0:
                    energy_ratio = actual_energy / expected_energy
                    validation_results["consistency_checks"]["energy_calculation_consistent"] = (
                        0.8 <= energy_ratio <= 1.2  # Should be very close
                    )
                    validation_results["consistency_checks"]["energy_ratio"] = energy_ratio
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Failed to validate metrics consistency: {e}")
            return {"status": "error", "message": str(e)}


def get_telemetry_service(db: AsyncSession) -> TelemetryService:
    """Dependency to get telemetry service"""
    return TelemetryService(db)
