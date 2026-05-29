FROM python:3.11-slim

WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY . .

# Port d'écoute
EXPOSE 8084

# Lancement de l'application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8084"]
