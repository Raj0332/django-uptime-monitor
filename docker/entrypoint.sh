#!/bin/sh
set -e

case "$1" in
  web)
    echo "Running migrations..."
    python manage.py makemigrations monitor --noinput
    python manage.py migrate --noinput
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
    echo "Starting Gunicorn..."
    exec gunicorn uptime.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers 3 \
      --worker-class sync \
      --timeout 30 \
      --access-logfile - \
      --error-logfile - \
      --log-level info
    ;;
  worker)
    echo "Starting Celery worker..."
    exec celery -A uptime worker \
      --loglevel=info \
      --concurrency=4 \
      -E
    ;;
  beat)
    echo "Starting Celery beat..."
    exec celery -A uptime beat \
      --loglevel=info \
      --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;
  *)
    exec "$@"
    ;;
esac
