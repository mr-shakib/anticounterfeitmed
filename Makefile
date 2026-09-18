# Developer entry points. See docs/12 for deployed environments.
PY := .venv/bin/python
COMPOSE := docker compose -f infra/docker-compose.dev.yml

.PHONY: help up down migrate test vectors vectors-regen crosscheck leakcheck landing-csp labels serve operator seed check

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

serve:  ## Run the dev server at http://127.0.0.1:8000 (admin at /admin/)
	DJANGO_DEBUG=1 $(PY) backend/manage.py runserver 127.0.0.1:8000

operator:  ## Create the local platform-operator admin account
	DJANGO_DEBUG=1 $(PY) backend/manage.py createsuperuser

seed:  ## Seed a demo manufacturer, batch and activated units
	DJANGO_DEBUG=1 $(PY) backend/manage.py seed_demo --count 3

landing-csp:  ## Recompute the landing page CSP hashes into landing/nginx.conf
	$(PY) scripts/build_landing_csp.py

labels:  ## Generate the printable physical QR test sheet (80 labels)
	$(PY) spikes/s1-qr/generate_test_labels.py

operator:  ## Create the local platform-operator admin account
	DJANGO_DEBUG=1 $(PY) backend/manage.py createsuperuser

staff:  ## Create the demo portal accounts (admin + release manager)
	DJANGO_DEBUG=1 $(PY) backend/manage.py create_staff demo-admin --role PLATFORM_ADMIN
	DJANGO_DEBUG=1 $(PY) backend/manage.py create_staff demo-release-manager --role RELEASE_MANAGER

staff-code:  ## Print a current second-factor code: make staff-code USER=demo-admin
	@DJANGO_DEBUG=1 $(PY) backend/manage.py staff_code $(USER)

seed:  ## Seed demo data (development only)
	DJANGO_DEBUG=1 $(PY) backend/manage.py seed_demo --count 3

serve:  ## Run the backend, admin at http://127.0.0.1:8000/admin/
	DJANGO_DEBUG=1 $(PY) backend/manage.py runserver 127.0.0.1:8000

serve-nomfa:  ## Same, but without the staff second factor (DEBUG only)
	DJANGO_DEBUG=1 STAFF_MFA_REQUIRED=0 $(PY) backend/manage.py runserver 127.0.0.1:8000

apk:  ## Build the Android self-check APK into dist/
	cd consumer-app && flutter build apk --release --target-platform=android-arm64
	mkdir -p dist
	cp consumer-app/build/app/outputs/flutter-apk/app-release.apk dist/anticounterfeitmed-selfcheck-arm64.apk
	@sha256sum dist/anticounterfeitmed-selfcheck-arm64.apk

backup:  ## Take an encrypted backup into ./backups
	BACKUP_PASSPHRASE=$${BACKUP_PASSPHRASE} ./infra/backup.sh ./backups

restore-drill:  ## Restore the newest backup in isolation and verify it (docs/11)
	./infra/restore-drill.sh $$(ls -t ./backups/*.dump* 2>/dev/null | head -1)

brand:  ## Regenerate every sized copy of the project mark
	$(PY) scripts/build_brand_assets.py
	$(PY) scripts/build_landing_csp.py
	cp landing/nginx.conf infra/nginx/conf.d/site.conf

check: test vectors crosscheck leakcheck  ## Everything CI runs
	@echo "all checks passed"
