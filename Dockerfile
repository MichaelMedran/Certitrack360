FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Servidor de producción (RF-51): «manage.py servir» arranca waitress y WhiteNoise sirve los estáticos
# (cierra la decisión abierta n.º 8 del SDD v1.0). El puerto y los hilos salen de SERVIDOR_PUERTO y SERVIDOR_HILOS.
CMD ["sh", "-c", "python manage.py esperar_bd && python manage.py migrate && python manage.py servir"]
