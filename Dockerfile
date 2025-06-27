FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VENV_IN_PROJECT=1
ENV POETRY_CACHE_DIR=/tmp/poetry_cache

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        postgresql-client \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

RUN poetry config virtualenvs.in-project true

# Copy application code
COPY . .

# Install the application
RUN poetry install --no-root

# Expose port
EXPOSE 8000
