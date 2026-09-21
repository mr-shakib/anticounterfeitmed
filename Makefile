# Developer entry points. See docs/17 for the full local setup, and docs/12 for
# deployed environments.
PY := .venv/bin/python
COMPOSE := docker compose -f infra/docker-compose.dev.yml

.PHONY: help \
        up down stop migrate \
        serve serve-nomfa seed staff staff-code operator \
        test vectors vectors-regen crosscheck leakcheck check \
        apk apk-dev labels brand landing-csp \
        backup restore-drill

help:  ## List these targets
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- dependencies -----------------------------------------------------------

up:  ## Start PostgreSQL and Redis, and wait until they accept connections
	$(COMPOSE) up -d
	@until docker exec acm_postgres pg_isready -U acm -d acm >/dev/null 2>&1; do sleep 1; done
	@echo "database ready"

down:  ## Stop PostgreSQL and Redis
	$(COMPOSE) down

stop:  ## Stop stray local dev servers (backend, portal, signer)
	@./scripts/stop_dev_servers.sh

migrate:  ## Apply database migrations
	$(PY) backend/manage.py migrate

# --- running ----------------------------------------------------------------

serve:  ## Run the backend at http://127.0.0.1:8000 (admin at /admin/)
	DJANGO_DEBUG=1 $(PY) backend/manage.py runserver 127.0.0.1:8000

serve-nomfa:  ## Run the backend without the staff second factor (DEBUG only)
	DJANGO_DEBUG=1 STAFF_MFA_REQUIRED=0 $(PY) backend/manage.py runserver 127.0.0.1:8000

# --- local data and accounts ------------------------------------------------

seed:  ## Seed a demo manufacturer, batch and activated units
	DJANGO_DEBUG=1 $(PY) backend/manage.py seed_demo --count 3

staff:  ## Create or reset the three demo portal accounts, one per role
	DJANGO_DEBUG=1 $(PY) backend/manage.py create_staff demo-admin --role PLATFORM_ADMIN
	DJANGO_DEBUG=1 $(PY) backend/manage.py create_staff demo-release-manager --role RELEASE_MANAGER
	DJANGO_DEBUG=1 $(PY) backend/manage.py create_staff demo-staff --role MANUFACTURER_STAFF

staff-reset-mfa:  ## Clear a second factor so it can be re-enrolled: make staff-reset-mfa USER=demo-admin
	DJANGO_DEBUG=1 $(PY) backend/manage.py create_staff $(USER) --reset-mfa

staff-code:  ## Print a second-factor code: make staff-code USER=demo-admin
	@DJANGO_DEBUG=1 $(PY) backend/manage.py staff_code $(USER)

operator:  ## Create a Django admin superuser (not a portal account)
	DJANGO_DEBUG=1 $(PY) backend/manage.py createsuperuser

# --- tests ------------------------------------------------------------------

test:  ## Run the backend suite against real PostgreSQL
	$(PY) -m pytest

vectors:  ## Verify the golden crypto vectors
	$(PY) crypto-vectors/verify.py

vectors-regen:  ## Regenerate the golden vectors (only when a schema changes)
	$(PY) crypto-vectors/generate.py

crosscheck:  ## Verify the vectors with the system OpenSSL binary
	./crypto-vectors/crosscheck_openssl.sh

leakcheck:  ## Fail if anything resembling a raw token is tracked by git
	./scripts/check_no_token_leak.sh

check: test vectors crosscheck leakcheck  ## Everything CI runs
	@echo "all checks passed"

# --- build artefacts --------------------------------------------------------

# A release APK is a distributable artefact: it is signed with the upload key,
# points at a real API, and carries the Firebase project that App Check attests
# against. None of that has a safe default, so each is required rather than
# guessed. See consumer-app/README.md.
APK_REQUIRED := BACKEND_BASE_URL ROOT_PUBLIC_KEY FIREBASE_PROJECT_ID FIREBASE_APP_ID FIREBASE_API_KEY FIREBASE_MESSAGING_SENDER_ID
# All three ABIs by default: 32-bit phones are common in the pilot market and an
# arm64-only APK will not install on them. Narrow it for a quicker local build.
APK_PLATFORMS ?= android-arm64,android-arm,android-x64

apk:  ## Build the signed release APK into dist/ (see consumer-app/README.md for the variables)
	@missing=""; for v in $(APK_REQUIRED); do \
	  eval "val=\$$$$v"; [ -n "$$val" ] || missing="$$missing $$v"; \
	done; \
	if [ -n "$$missing" ]; then \
	  echo "make apk needs:$$missing"; \
	  echo "See consumer-app/README.md. For a development build, use: make apk-dev"; \
	  exit 1; \
	fi
	cd consumer-app && flutter build apk --release --target-platform=$(APK_PLATFORMS) \
	  --dart-define=BACKEND_BASE_URL="$(BACKEND_BASE_URL)" \
	  --dart-define=ROOT_PUBLIC_KEY="$(ROOT_PUBLIC_KEY)" \
	  --dart-define=FIREBASE_PROJECT_ID="$(FIREBASE_PROJECT_ID)" \
	  --dart-define=FIREBASE_APP_ID="$(FIREBASE_APP_ID)" \
	  --dart-define=FIREBASE_API_KEY="$(FIREBASE_API_KEY)" \
	  --dart-define=FIREBASE_MESSAGING_SENDER_ID="$(FIREBASE_MESSAGING_SENDER_ID)"
	@mkdir -p dist
	cp consumer-app/build/app/outputs/flutter-apk/app-release.apk dist/anticounterfeitmed-consumer.apk
	@sha256sum dist/anticounterfeitmed-consumer.apk

apk-dev:  ## Build a profile APK for sideloaded development. Not distributable.
	cd consumer-app && flutter build apk --profile --target-platform=$(APK_PLATFORMS) \
	  --dart-define=BACKEND_BASE_URL="$(or $(BACKEND_BASE_URL),http://10.0.2.2:8000)" \
	  --dart-define=ROOT_PUBLIC_KEY="$(ROOT_PUBLIC_KEY)"
	@mkdir -p dist
	cp consumer-app/build/app/outputs/flutter-apk/app-profile.apk dist/anticounterfeitmed-consumer-dev.apk
	@echo "Development build: debug-signed, and it sends the placeholder attestation token."

labels:  ## Generate the printable physical QR test sheet (80 labels)
	$(PY) spikes/s1-qr/generate_test_labels.py

brand:  ## Regenerate every sized copy of the project mark
	$(PY) scripts/build_brand_assets.py
	$(PY) scripts/build_landing_csp.py
	cp landing/nginx.conf infra/nginx/conf.d/site.conf

landing-csp:  ## Recompute the landing page CSP hashes after editing the page
	$(PY) scripts/build_landing_csp.py
	cp landing/nginx.conf infra/nginx/conf.d/site.conf

# --- backup and recovery ----------------------------------------------------

backup:  ## Take an encrypted database backup into ./backups
	BACKUP_PASSPHRASE=$${BACKUP_PASSPHRASE} ./infra/backup.sh ./backups

restore-drill:  ## Restore the newest backup in isolation and verify it (docs/11)
	./infra/restore-drill.sh $$(ls -t ./backups/*.dump* 2>/dev/null | head -1)
