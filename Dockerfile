FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home app
COPY --chown=app:app advertisements ./advertisements
USER app

EXPOSE 8080
CMD ["python", "-m", "advertisements", "--host", "0.0.0.0", "--port", "8080"]
