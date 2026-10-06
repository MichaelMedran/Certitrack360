FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Servidor de desarrollo de Django: suficiente para la demostración en una red local.
# Servir en producción con gunicorn y WhiteNoise es la decisión abierta n.º 8 del SDD (pendiente de confirmar).
CMD ["sh", "-c", "python manage.py esperar_bd && python manage.py migrate && python manage.py runserver 0.0.0.0:8000 --noreload --insecure"]
