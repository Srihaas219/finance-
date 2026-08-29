.PHONY: help up down reset seed demo-seed demo-reset backend-install backend-test frontend-install frontend-build frontend-e2e test

help:
	@echo "up             - docker compose up --build (db + api + web)"
	@echo "down           - docker compose down"
	@echo "reset          - docker compose down -v (wipe volumes)"
	@echo "seed           - seed demo users into the running/api DB"
	@echo "demo-seed      - ingest loan tape + servicer feed + run validation (populated demo)"
	@echo "demo-reset     - reset volumes, rebuild, and populate deterministic demo data"
	@echo "backend-test   - run backend pytest suite"
	@echo "frontend-build - typecheck + build frontend"
	@echo "frontend-e2e   - Playwright browser E2E (requires Docker on :8000/:8080)"
	@echo "test           - backend tests + frontend build"

up:
	docker compose up --build

down:
	docker compose down

reset:
	docker compose down -v

seed:
	docker compose exec api python -m app.seed

demo-seed:
	docker compose exec api python -m app.demo_seed

demo-reset:
	docker compose down -v
	docker compose up --build -d
	@echo "Waiting for API…" && sleep 12
	docker compose exec -T api python -m app.demo_seed
	@echo "Fresh deterministic demo environment populated (1000 loans validated)."

backend-install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

backend-test:
	cd backend && . .venv/bin/activate && python -m pytest

frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm run build

frontend-e2e:
	cd frontend && npx playwright test e2e/

test: backend-test frontend-build
