dev:
	python backend/manage.py runserver 127.0.0.1:8011
build:
	npm --prefix frontend run build
up:
	docker compose up -d
down:
	docker compose down
logs:
	docker compose logs --tail 100 -f
test:
	cd backend && pytest
	npm --prefix frontend test
