FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./

RUN pip install \
    "aiogram>=3.27,<4" \
    "aiosqlite>=0.20" \
    "httpx>=0.27" \
    "asyncpg>=0.29" \
    "python-dotenv>=1.0" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.4" \
    "boto3>=1.34" \
    "aiohttp>=3.9"

COPY app ./app

VOLUME ["/data"]

CMD ["python", "-m", "app.main"]
