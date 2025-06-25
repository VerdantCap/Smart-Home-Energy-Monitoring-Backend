# Smart Home Unified Service

A unified FastAPI service that combines Authentication, AI, and Telemetry functionality for the Smart Home Energy Monitoring system.

## Overview

This service consolidates three previously separate microservices into a single, unified application:

- **Authentication Service**: User registration, login, JWT token management
- **AI Service**: Conversational AI for energy data queries using OpenAI
- **Telemetry Service**: Energy consumption data ingestion and analytics

## Features

### Authentication Module
- User registration and login
- JWT token-based authentication
- Password reset functionality
- Role-based access control (user/admin)
- Token revocation and blacklisting

### AI Module
- Natural language queries about energy data
- Conversation history management
- OpenAI integration for intelligent responses
- Query caching and rate limiting
- Suggested questions and examples

### Telemetry Module
- Energy consumption data ingestion
- Real-time metrics and analytics
- Device management
- Batch data processing
- Historical data analysis

## API Endpoints

### Authentication Endpoints
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - User login
- `GET /api/v1/auth/me` - Get current user profile
- `PUT /api/v1/auth/me` - Update user profile
- `POST /api/v1/auth/change-password` - Change password
- `POST /api/v1/auth/logout` - Logout user

### AI/Chat Endpoints
- `POST /api/v1/chat/query` - Process natural language query
- `GET /api/v1/chat/conversation` - Get conversation history
- `DELETE /api/v1/chat/conversation` - Clear conversation history
- `GET /api/v1/chat/suggestions` - Get suggested questions
- `GET /api/v1/chat/examples` - Get query examples

### Telemetry Endpoints
- `POST /api/v1/telemetry/` - Create telemetry record
- `POST /api/v1/telemetry/batch` - Batch create telemetry records
- `GET /api/v1/telemetry/` - Get telemetry data with filtering
- `GET /api/v1/telemetry/stats/{device_id}` - Get device statistics
- `GET /api/v1/telemetry/summary` - Get energy consumption summary
- `GET /api/v1/telemetry/realtime` - Get real-time metrics
- `GET /api/v1/telemetry/devices` - Get user devices

### Health Check Endpoints
- `GET /api/health` - Main service health check
- `GET /api/auth/health` - Auth module health check
- `GET /api/chat/health` - AI module health check
- `GET /api/telemetry/health` - Telemetry module health check

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/smart_home_energy

# JWT
JWT_SECRET_KEY=your-super-secret-jwt-key
JWT_EXPIRE_MINUTES=1440

# Redis
REDIS_URL=redis://localhost:6379

# OpenAI (for AI functionality)
OPENAI_API_KEY=your-openai-api-key-here

# Service Configuration
PORT=8000
DEBUG=false
ALLOWED_HOSTS=["*"]
```

## Installation

### Using Docker (Recommended)

1. Build and run with docker-compose:
```bash
docker-compose up --build
```

### Local Development

1. Install dependencies:
```bash
poetry install
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run the service:
```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Dependencies

- **FastAPI**: Web framework
- **SQLAlchemy**: Database ORM
- **PostgreSQL**: Database
- **Redis**: Caching and session storage
- **OpenAI**: AI functionality
- **JWT**: Authentication tokens
- **Pydantic**: Data validation
- **Uvicorn**: ASGI server

## Architecture

The unified service maintains a modular architecture:

```
backend/
├── app/
│   ├── api/v1/endpoints/
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── chat.py          # AI/Chat endpoints
│   │   └── telemetry.py     # Telemetry endpoints
│   ├── core/
│   │   ├── config.py        # Configuration settings
│   │   ├── database.py      # Database connection
│   │   ├── deps.py          # Dependencies and auth
│   │   ├── redis_client.py  # Redis client
│   │   └── security.py      # Security utilities
│   ├── models/              # Database models
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business logic
│   └── main.py              # Application entry point
├── Dockerfile
└── pyproject.toml
```

## Rate Limiting

The service implements rate limiting at multiple levels:

- **Authentication**: 5 requests per 5 minutes
- **General**: 100 requests per hour
- **Chat**: 50 requests per hour per user
- **Telemetry**: 1000 requests per hour per user

## Security Features

- JWT token-based authentication
- Password hashing with bcrypt
- Token revocation and blacklisting
- Role-based access control
- Rate limiting
- CORS protection
- Input validation

## Monitoring and Health Checks

The service provides comprehensive health checks:

- Database connectivity
- Redis connectivity
- OpenAI API status
- Service-specific metrics
