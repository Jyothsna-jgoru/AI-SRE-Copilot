.PHONY: setup up down logs test lint demo

setup:
	python -c "from pathlib import Path; p=Path('.env'); p.write_text(Path('.env.example').read_text()) if not p.exists() else None"

up: setup
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f backend worker mcp-server frontend

test:
	pytest --cov=backend --cov=agents --cov=simulator --cov-report=term-missing

lint:
	ruff check .

demo:
	python -m http.server 8080 --directory demo

