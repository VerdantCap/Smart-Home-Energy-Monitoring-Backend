from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


class Telemetry(Base):
    """Telemetry model for device power consumption data"""
    
    __tablename__ = "telemetry"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(String(255), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    energy_watts = Column(Numeric(10, 3), nullable=False)  # Note: Despite the name, this stores instantaneous power in watts
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<Telemetry(device_id={self.device_id}, timestamp={self.timestamp}, power_watts={self.energy_watts})>"
    
    def to_dict(self) -> dict:
        """Convert telemetry to dictionary"""
        return {
            "id": str(self.id),
            "device_id": self.device_id,
            "user_id": str(self.user_id),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "energy_watts": float(self.energy_watts) if self.energy_watts else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TelemetryHourlyAggregate(Base):
    """Hourly aggregated telemetry data for performance"""
    
    __tablename__ = "telemetry_hourly_aggregates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(String(255), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    hour_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    avg_energy_watts = Column(Numeric(10, 3), nullable=False)
    min_energy_watts = Column(Numeric(10, 3), nullable=False)
    max_energy_watts = Column(Numeric(10, 3), nullable=False)
    total_energy_wh = Column(Numeric(12, 3), nullable=False)
    sample_count = Column(Numeric(10, 0), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<TelemetryHourlyAggregate(device_id={self.device_id}, hour={self.hour_timestamp}, avg_watts={self.avg_energy_watts})>"
    
    def to_dict(self) -> dict:
        """Convert hourly aggregate to dictionary"""
        return {
            "id": str(self.id),
            "device_id": self.device_id,
            "user_id": str(self.user_id),
            "hour_timestamp": self.hour_timestamp.isoformat() if self.hour_timestamp else None,
            "avg_energy_watts": float(self.avg_energy_watts) if self.avg_energy_watts else None,
            "min_energy_watts": float(self.min_energy_watts) if self.min_energy_watts else None,
            "max_energy_watts": float(self.max_energy_watts) if self.max_energy_watts else None,
            "total_energy_wh": float(self.total_energy_wh) if self.total_energy_wh else None,
            "sample_count": int(self.sample_count) if self.sample_count else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
