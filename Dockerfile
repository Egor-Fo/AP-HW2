FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt requirements.txt
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV TOKEN_TG = "7942018113:AAGYR7uWKjxNQSwKLsYF22UCVsHOiPW4rTU"
ENV WEATHER_TOKEN="43448e0861ee2072f496f6855f930d44"

CMD ["python", "bot.py"]
