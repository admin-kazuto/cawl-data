# ── Base image ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Encoding fix cho Windows terminal
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1

# ── Cài dependencies ─────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy source code ──────────────────────────────────────────────────────────
COPY . .

# ── Expose port ───────────────────────────────────────────────────────────────
EXPOSE 7000

# ── Chạy server ───────────────────────────────────────────────────────────────
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7000"]
