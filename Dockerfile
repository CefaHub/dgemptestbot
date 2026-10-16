FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY . .

# Fail the Docker build if the card catalogue is missing in the image.
RUN python -c "from dolce_empire.catalog import all_cards; print('DOLCE EMPIRE catalogue:', len(all_cards()), 'cards')"

CMD ["python", "main.py"]
