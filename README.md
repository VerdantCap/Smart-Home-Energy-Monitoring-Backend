# Smart Home Energy Monitoring Backend

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

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for local development)
- PostgreSQL 15+ (if running locally)
- Redis 7+ (if running locally)

### Using Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Smart-Home-Energy-Monitoring-Backend
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` file with your configuration:
   ```bash
   # Database Configuration
   POSTGRES_DB=smart_home_energy
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=your_secure_password_here
   DATABASE_URL=postgresql+asyncpg://postgres:your_secure_password_here@postgres:5432/smart_home_energy

   # JWT Configuration
   JWT_SECRET_KEY=your-super-secure-jwt-secret-key-here
   JWT_EXPIRE_MINUTES=1440

   # OpenAI Configuration
   OPENAI_API_KEY=your-openai-api-key-here

   # Application Settings
   DEBUG=false
   PORT=8000
   LOG_LEVEL=INFO

   # Redis Configuration
   REDIS_URL=redis://redis:6379

   # Rate Limiting
   RATE_LIMIT_WINDOW_MS=100
   RATE_LIMIT_MAX_REQUESTS=1000

   # Security
   ALLOWED_HOSTS=["*"]
   ```

3. **Start all services**
   ```bash
   docker-compose up -d
   ```

4. **Verify services are running**
   ```bash
   docker-compose ps
   ```

5. **Access the API**
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/api/health

### Local Development Setup

1. **Install Poetry** (if not already installed)
   ```bash
   pip install poetry 
   ```

2. **Install dependencies**
   ```bash

   poetry env activate

   poetry install --no-root
   ```

3. **Set up local database and Redis**
   ```bash
   # Start only database and Redis services
   docker-compose up -d postgres redis
   ```

4. **Update .env for local development**
   ```bash
   DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/smart_home_energy
   REDIS_URL=redis://localhost:6379
   ```

5. **Run database migrations**
   ```bash
   poetry run alembic upgrade head
   ```

6. **Start the development server**
   ```bash
   poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

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

## Architecture

```
Smart-Home-Energy-Monitoring-Backend/
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
│   │   ├── security.py      # Security utilities
│   │   └── logging.py       # Logging configuration
│   ├── models/              # Database models
│   │   ├── user.py
│   │   ├── device.py
│   │   └── telemetry.py
│   ├── schemas/             # Pydantic schemas
│   │   ├── user.py
│   │   ├── chat.py
│   │   └── telemetry.py
│   ├── services/            # Business logic
│   │   ├── user_service.py
│   │   ├── ai_service.py
│   │   └── telemetry_service.py
│   └── main.py              # Application entry point
├── alembic/                 # Database migrations
├── scripts/                 # Utility scripts
│   └── simulate-telemetry.py
├── docker-compose.yml       # Docker services
├── Dockerfile              # Container definition
├── pyproject.toml          # Python dependencies
└── .env.example            # Environment template
```

## Testing

### Running the Telemetry Simulator

The project includes a telemetry data simulator for testing:

```bash
# Run simulator as part of docker-compose
docker-compose up -d simulator

# Or run manually
poetry run python scripts/simulate-telemetry.py
```

### API Testing

Use the interactive API documentation at http://localhost:8000/docs to test endpoints.

## Tech Stack

- **Backend**: FastAPI, Python 3.11+
- **Database**: PostgreSQL 15
- **Cache**: Redis 7
- **ORM**: SQLAlchemy with Alembic migrations
- **Authentication**: JWT tokens
- **AI**: OpenAI GPT integration
- **Containerization**: Docker & Docker Compose
- **Documentation**: OpenAPI/Swagger
- **Validation**: Pydantic
- **Server**: Uvicorn ASGI