#!/bin/sh
set -e

# Run Django migrations. In Kubernetes this is done ONCE by the migrate Job /
# Helm hook, so web pods set RUN_MIGRATIONS_ON_START=false and skip it here —
# otherwise every web replica would race to migrate on `helm upgrade` / scale-up.
# In docker-compose the var is unset, so it defaults to "true" and web migrates
# on start exactly as before.
run_migrations() {
  echo "Running migrations..."
  python manage.py makemigrations monitor --noinput
  python manage.py migrate --noinput
}

case "$1" in
  web)
    if [ "${RUN_MIGRATIONS_ON_START:-true}" = "true" ]; then
      run_migrations
    fi

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

  migrate)
    run_migrations
    ;;

  worker)
    exec celery -A uptime worker --loglevel=info --concurrency=4 -E
    ;;

  beat)
    exec celery -A uptime beat \
      --loglevel=info \
      --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;

  *)
    exec "$@"
    ;;
esac
