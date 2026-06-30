FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend

COPY backend/requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY frontend/ ../frontend/

RUN mkdir -p uploads/resumes

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]