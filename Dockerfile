FROM python:3.12-slim
WORKDIR /app
COPY bot.py /app/bot.py
COPY whale_alerts.py /app/whale_alerts.py
ENV PYTHONUNBUFFERED=1 STATE_FILE=/app/data/state.json
CMD ["python", "bot.py"]
