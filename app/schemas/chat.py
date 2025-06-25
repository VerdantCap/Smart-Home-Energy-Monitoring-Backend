from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class ChatMessage(BaseModel):
    """Schema for a chat message"""
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=2000)
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    """Schema for chat request"""
    message: str = Field(..., min_length=1, max_length=500, description="User's question or message")
    conversation_id: Optional[str] = Field(None, description="Optional conversation ID for context")
    include_context: bool = Field(True, description="Whether to include conversation context")


class ChatResponse(BaseModel):
    """Schema for chat response"""
    message: str = Field(..., description="AI assistant's response")
    conversation_id: str = Field(..., description="Conversation ID for tracking")
    timestamp: datetime = Field(..., description="Response timestamp")
    data_sources: Optional[List[str]] = Field(None, description="Data sources used for the response")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score")
    suggested_questions: Optional[List[str]] = Field(None, description="Suggested follow-up questions")


class ConversationHistory(BaseModel):
    """Schema for conversation history"""
    conversation_id: str
    messages: List[ChatMessage]
    created_at: datetime
    updated_at: datetime
    user_id: str


class QueryIntent(BaseModel):
    """Schema for parsed query intent"""
    intent_type: str = Field(..., description="Type of intent (device_stats, energy_summary, etc.)")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    time_range: Optional[Dict[str, str]] = Field(None, description="Time range for the query")
    device_ids: Optional[List[str]] = Field(None, description="Specific device IDs mentioned")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Intent recognition confidence")


class EnergyInsight(BaseModel):
    """Schema for energy insights"""
    insight_type: str = Field(..., description="Type of insight")
    title: str = Field(..., description="Insight title")
    description: str = Field(..., description="Detailed description")
    value: Optional[float] = Field(None, description="Numerical value if applicable")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    recommendation: Optional[str] = Field(None, description="Recommendation based on insight")
    priority: str = Field("medium", pattern="^(low|medium|high)$", description="Priority level")


class DeviceAnalysis(BaseModel):
    """Schema for device analysis"""
    device_id: str
    device_name: Optional[str]
    analysis_type: str
    findings: List[str]
    recommendations: List[str]
    efficiency_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    cost_impact: Optional[float] = Field(None, description="Estimated cost impact")


class SmartRecommendation(BaseModel):
    """Schema for smart recommendations"""
    recommendation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    category: str = Field(..., description="Category of recommendation")
    potential_savings: Optional[float] = Field(None, description="Potential energy/cost savings")
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    estimated_time: Optional[str] = Field(None, description="Estimated time to implement")
    priority: str = Field("medium", pattern="^(low|medium|high)$")


class ConversationSummary(BaseModel):
    """Schema for conversation summary"""
    conversation_id: str
    user_id: str
    message_count: int
    topics_discussed: List[str]
    key_insights: List[str]
    recommendations_given: List[str]
    duration_minutes: Optional[float]
    created_at: datetime
    last_activity: datetime


class AIServiceHealth(BaseModel):
    """Schema for AI service health"""
    service: str
    status: str
    timestamp: datetime
    openai_status: str
    redis_status: str
    telemetry_service_status: str
    auth_service_status: str
    active_conversations: int
    total_queries_today: int
    average_response_time_ms: float


class QueryAnalytics(BaseModel):
    """Schema for query analytics"""
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    query_text: str
    intent_detected: str
    confidence_score: float
    response_time_ms: float
    data_sources_used: List[str]
    success: bool
    error_message: Optional[str] = None
    timestamp: datetime


class ContextualResponse(BaseModel):
    """Schema for contextual AI response with data"""
    response_text: str = Field(..., description="Natural language response")
    data_summary: Optional[Dict[str, Any]] = Field(None, description="Structured data summary")
    charts_data: Optional[List[Dict[str, Any]]] = Field(None, description="Data for charts/visualizations")
    insights: Optional[List[EnergyInsight]] = Field(None, description="Generated insights")
    recommendations: Optional[List[SmartRecommendation]] = Field(None, description="Smart recommendations")
    follow_up_questions: Optional[List[str]] = Field(None, description="Suggested follow-up questions")


class BulkChatRequest(BaseModel):
    """Schema for bulk chat processing"""
    messages: List[str] = Field(..., max_items=10, description="Multiple messages to process")
    conversation_id: Optional[str] = None
    parallel_processing: bool = Field(False, description="Whether to process messages in parallel")


class BulkChatResponse(BaseModel):
    """Schema for bulk chat response"""
    responses: List[ChatResponse]
    conversation_id: str
    total_processing_time_ms: float
    successful_responses: int
    failed_responses: int


class ConversationExport(BaseModel):
    """Schema for conversation export"""
    conversation_id: str
    user_email: str
    messages: List[ChatMessage]
    insights_generated: List[EnergyInsight]
    recommendations_given: List[SmartRecommendation]
    export_format: str = Field("json", pattern="^(json|csv|pdf)$")
    exported_at: datetime


class AIModelConfig(BaseModel):
    """Schema for AI model configuration"""
    model_name: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1, le=4000)
    top_p: float = Field(ge=0.0, le=1.0, default=1.0)
    frequency_penalty: float = Field(ge=-2.0, le=2.0, default=0.0)
    presence_penalty: float = Field(ge=-2.0, le=2.0, default=0.0)
    system_prompt: Optional[str] = None


class ConversationMetrics(BaseModel):
    """Schema for conversation metrics"""
    total_conversations: int
    active_conversations: int
    average_conversation_length: float
    most_common_intents: List[Dict[str, Any]]
    user_satisfaction_score: Optional[float] = Field(None, ge=0.0, le=5.0)
    response_time_percentiles: Dict[str, float]
    error_rate: float = Field(ge=0.0, le=1.0)
