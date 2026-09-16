# Developer entry points. See docs/12 for deployed environments.
PY := .venv/bin/python
COMPOSE := docker compose -f infra/docker-compose.dev.yml

.PHONY: help up down migrate test vectors vectors-regen crosscheck leakcheck landing-csp labels check

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up:  ## Start PostgreSQL and Redis
	$(COMPOSE) up -d
	@until docker exec acm_postgres pg_isready -U acm -d acm >/dev/null 2>&1; do sleep 1; done
	@echo "database ready"

down:  ## Stop development dependencies
	$(COMPOSE) down

migrate:  ## Apply migrations
	$(PY) backend/manage.py migrate

test:  ## Run the full test suite against real PostgreSQL
	$(PY) -m pytest

vectors:  ## Verify the golden crypto vectors
	$(PY) crypto-vectors/verify.py

vectors-regen:  ## Regenerate the golden vectors (only when a schema changes)
	$(PY) crypto-vectors/generate.py

crosscheck:  ## Verify the vectors with the system OpenSSL binary
	./crypto-vectors/crosscheck_openssl.sh

leakcheck:  ## Fail if anything that looks like a raw token is committed
	./scripts/check_no_token_leak.sh

landing-csp:  ## Recompute the landing page CSP hashes into landing/nginx.conf
	$(PY) scripts/build_landing_csp.py

labels:  ## Generate the printable physical QR test sheet (80 labels)
	$(PY) spikes/s1-qr/generate_test_labels.py

check: test vectors crosscheck leakcheck  ## Everything CI runs
	@echo "all checks passed"
