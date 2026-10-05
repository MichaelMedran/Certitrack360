FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
RUN python manage.py collectstatic --noinput
CMD ["sh", "-c", "python manage.py migrate && gunicorn certitrack.wsgi:application -b 0.0.0.0:8000"]
