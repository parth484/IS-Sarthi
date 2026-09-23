.PHONY: up down bootstrap api ui demo test workers beat validate-selectors

up:            ## start infrastructure
	cd deploy && docker compose up -d

down:
	cd deploy && docker compose down

bootstrap:     ## load seed corpus + build indices
	python scripts/bootstrap.py

api:
	uvicorn api.main:app --reload --port 8000

ui:
	streamlit run ui/app.py

demo:          ## zero-infrastructure demo
	python scripts/demo_offline.py

test:
	pytest tests/ -v

workers:
	celery -A pipeline.celery_app worker -Q scrape  --concurrency=4 --loglevel=info &
	celery -A pipeline.celery_app worker -Q process --concurrency=2 --loglevel=info &
	celery -A pipeline.celery_app worker -Q embed   --concurrency=2 --loglevel=info

beat:
	celery -A pipeline.celery_app beat --loglevel=info

validate-selectors:
	python scripts/validate_selectors.py
