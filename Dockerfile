# Uses official Playwright image (includes Chromium and system deps)
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py app.py ./
COPY templates/ templates/

# Create dirs the app writes to (can be overridden by mounts)
RUN mkdir -p runs

ENV PORT=8080
EXPOSE 8080

# Railway/Render set PORT; use 0.0.0.0 so the server is reachable
CMD ["python", "app.py"]
