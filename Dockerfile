FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/appuser \
    HF_HOME=/home/appuser/.cache/huggingface

WORKDIR /app

RUN useradd --create-home --uid 1000 appuser

COPY requirements.txt /tmp/project-constraints.txt
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install \
        --constraint /tmp/project-constraints.txt \
        --requirement /tmp/backend-requirements.txt

COPY --chown=appuser:appuser backend /app/backend
COPY --chown=appuser:appuser rag /app/rag

USER appuser

# 첫 챗봇 요청에서 모델을 새로 내려받느라 지연되지 않도록 이미지에 포함합니다.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"

EXPOSE 7860

CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
