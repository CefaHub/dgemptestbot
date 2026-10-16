FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN useradd --system --uid 10001 --create-home empire && mkdir -p /app/data && chown -R empire:empire /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=empire:empire dolce_empire /app/dolce_empire
COPY --chown=empire:empire data/catalog.json /app/data/catalog.json
COPY --chown=empire:empire assets/idols /app/assets/idols
USER empire
CMD ["python", "-m", "dolce_empire.bot"]
