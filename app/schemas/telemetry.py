from pydantic import BaseModel, Field, ConfigDict, validator
from typing import Optional, List
from datetime import datetime
import uuid


class TelemetryBase(BaseModel):
    """Base telemetry schema"""
    device_id: str = Field(..., min_length=1, max_length=255)
    timestamp: datetime
    energy_watts: float = Field(..., ge=0, le=50000, description="Instantaneous power consumption in watts (0-50kW max)")
    
    @validator('energy_watts')
    def validate_energy_watts(cls, v):
        if v < 0:
            raise ValueError('Power consumption cannot be negative')
        if v > 50000:  # 50kW maximum - reasonable for home devices
            raise ValueError('Power consumption exceeds maximum allowed value (50kW)')
        return round(v, 3)  # Round to 3 decimal places for consistency


class TelemetryCreate(TelemetryBase):
    """Schema for creating telemetry data"""
    pass


class TelemetryResponse(TelemetryBase):
    """Schema for telemetry response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime


class TelemetryBatch(BaseModel):
    """Schema for batch telemetry data"""
    telemetry_data: List[TelemetryCreate] = Field(..., max_items=1000)


class DeviceBase(BaseModel):
    """Base device schema"""
    device_id: str = Field(..., min_length=1, max_length=255)
    name: Optional[str] = Field(None, max_length=255)
    type: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)


class DeviceCreate(DeviceBase):
    """Schema for device creation"""
    pass


class DeviceUpdate(BaseModel):
    """Schema for device updates"""
    name: Optional[str] = Field(None, max_length=255)
    type: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class DeviceResponse(DeviceBase):
    """Schema for device response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    user_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TelemetryQuery(BaseModel):
    """Schema for telemetry queries"""
    device_ids: Optional[List[str]] = Field(None, description="Filter by device IDs")
    start_time: Optional[datetime] = Field(None, description="Start time for data range")
    end_time: Optional[datetime] = Field(None, description="End time for data range")
    limit: Optional[int] = Field(100, ge=1, le=10000, description="Maximum number of records")
    offset: Optional[int] = Field(0, ge=0, description="Number of records to skip")
    
    @validator('end_time')
    def validate_time_range(cls, v, values):
        if v and 'start_time' in values and values['start_time']:
            if v <= values['start_time']:
                raise ValueError('end_time must be after start_time')
        return v


class TelemetryStats(BaseModel):
    """Schema for telemetry statistics"""
    device_id: str
    device_name: Optional[str]
    total_energy_wh: float
    avg_energy_watts: float
    max_energy_watts: float
    min_energy_watts: float
    sample_count: int
    start_time: datetime
    end_time: datetime


class TelemetryAggregateResponse(BaseModel):
    """Schema for aggregated telemetry response"""
    device_id: str
    device_name: Optional[str]
    period: str  # "hour", "day", "week", "month"
    timestamp: datetime
    avg_energy_watts: float
    min_energy_watts: float
    max_energy_watts: float
    total_energy_wh: float
    sample_count: int


class EnergyConsumptionSummary(BaseModel):
    """Schema for energy consumption summary"""
    total_devices: int
    total_energy_wh: float
    avg_energy_watts: float
    peak_energy_watts: float
    peak_timestamp: Optional[datetime]
    period_start: datetime
    period_end: datetime
    top_consumers: List[TelemetryStats]


class DeviceEnergyTrend(BaseModel):
    """Schema for device energy trend"""
    device_id: str
    device_name: Optional[str]
    data_points: List[TelemetryAggregateResponse]
    trend_direction: str  # "increasing", "decreasing", "stable"
    trend_percentage: float


class RealTimeMetrics(BaseModel):
    """Schema for real-time metrics"""
    timestamp: datetime
    active_devices: int
    total_current_power: float
    average_power_per_device: float
    highest_consuming_device: Optional[str]
    highest_consumption: Optional[float]


class ExportRequest(BaseModel):
    """Schema for data export requests"""
    device_ids: Optional[List[str]] = None
    start_time: datetime
    end_time: datetime
    format: str = Field("csv", pattern="^(csv|json|xlsx)$")
    include_aggregates: bool = False
    
    @validator('end_time')
    def validate_export_time_range(cls, v, values):
        if v and 'start_time' in values and values['start_time']:
            if v <= values['start_time']:
                raise ValueError('end_time must be after start_time')
            # Limit export range to prevent large exports
            time_diff = v - values['start_time']
            if time_diff.days > 365:
                raise ValueError('Export range cannot exceed 365 days')
        return v


class HealthMetrics(BaseModel):
    """Schema for service health metrics"""
    service: str
    status: str
    timestamp: datetime
    database_status: str
    redis_status: str
    total_devices: int
    total_telemetry_records: int
    last_telemetry_timestamp: Optional[datetime]
    avg_requests_per_minute: float
