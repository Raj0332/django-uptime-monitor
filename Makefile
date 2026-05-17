.PHONY: up down logs build migrate superuser shell test lint format seed clean

COMPOSE = docker-compose

up:
	$(COMPOSE) up --build -d
	@echo "App running at http://localhost:8000"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

build:
	$(COMPOSE) build

migrate:
	$(COMPOSE) exec web python manage.py migrate

superuser:
	$(COMPOSE) exec web python manage.py createsuperuser

shell:
	$(COMPOSE) exec web python manage.py shell

test:
	$(COMPOSE) run --rm -e DATABASE_URL=sqlite:///test.db web \
		sh -c "pip install -r requirements-dev.txt -q && pytest --cov=monitor --cov-report=term-missing -v"

lint:
	$(COMPOSE) run --rm web sh -c "ruff check . && isort --check-only . && black --check --line-length 100 ."

format:
	$(COMPOSE) run --rm web sh -c "black --line-length 100 . && isort ."

seed:
	$(COMPOSE) exec web python manage.py shell -c "\
from django.contrib.auth.models import User; \
from monitor.models import Site; \
u = User.objects.filter(username='demo').first() or User.objects.create_user('demo','demo@example.com','demo1234'); \
Site.objects.get_or_create(user=u, url='https://www.google.com', defaults={'name':'Google','check_interval_seconds':60}); \
Site.objects.get_or_create(user=u, url='https://github.com', defaults={'name':'GitHub','check_interval_seconds':60}); \
print('Seed complete')"

clean:
	$(COMPOSE) down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf app/staticfiles app/.coverage htmlcov
