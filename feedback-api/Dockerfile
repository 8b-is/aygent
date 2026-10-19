FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py auth.py llm_assistant.py admin_panel.py storage.py ./

# Create feedback directory
RUN mkdir -p /app/feedback

# Run on port 8420 (Mem|8 standard)
EXPOSE 8420

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8420"]