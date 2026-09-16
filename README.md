# Anti-Counterfeit Medicine Verification

Development and effective application of AI-based, post-quantum cryptography-enabled counterfeit medicine identification tools for better treatment outcomes in Bangladesh.

**Status: pre-development.** No application code yet. Start at [docs/13-week-0-spikes.md](docs/13-week-0-spikes.md).

## What this system does

A manufacturer serializes each medicine package with a hidden QR code under a scratch layer. At release, the manufacturer signs an immutable **ML-DSA (FIPS 204)** activation credential for each unit. A consumer scratches the coating, scans with the official app, sees signed product information, and taps to record a **first verification**. That first verification is permanent and happens exactly once per unit.

A normal phone camera opening the same QR reaches a plain informational web page and changes nothing.

### What it does not do

It does **not** test the medicine's contents, prove a sale, or produce an automatic authenticity verdict. It checks a digital record. A copied QR redeemed before the genuine one is a **known, unsolved limitation** addressed by physical controls and investigation, not by cryptography. See [docs/01](docs/01-scope-and-roles.md) and [docs/07](docs/07-security-and-privacy.md).

## Documents

The authoritative requirements document is [`Medicine_Verification_Implementation_Plan.md`](Medicine_Verification_Implementation_Plan.md). **It wins any conflict.** The [`docs/`](docs/00-index.md) folder turns it into a buildable plan — start with [docs/00-index.md](docs/00-index.md).

## Planned layout

```text
backend/         Django + DRF — the only writer to PostgreSQL
signer/          Isolated ML-DSA signing service; holds private keys
staff-web/       Next.js — admin + manufacturer workspaces
landing/         Static public page, zero JS dependencies
consumer-app/    Flutter — Android first
crypto-vectors/  Golden signature vectors shared by all implementations
infra/           Compose files, deployment config, backup scripts
docs/            Planning and design documents
```

## Stack

Django 5.2 LTS · PostgreSQL 17 · Celery + Redis · Next.js 15 · Flutter · `cryptography` ≥ 50 for ML-DSA-65 · Firebase App Check.

The signer is **pure Python** — verified on 2026-09-16 that `cryptography` 50.0.1 exposes ML-DSA with enforced context strings, 3,309-byte signatures, and a bundled OpenSSL, so no native toolchain or system-OpenSSL dependency is needed. Details and the full measurement in [docs/03](docs/03-tech-stack.md).

## Three rules that must never bend

1. **Only `SHA-256(raw_token)` is stored.** Raw tokens live only in the print path and transient request memory — never in logs, audits, reports, or analytics.
2. **`REDEEMED` is permanent and happens exactly once per unit**, guaranteed by a PostgreSQL partial unique index, not by application logic.
3. **A successful scan never claims the medicine is genuine or safe** — only that the code matches the manufacturer's record.

## Scope boundaries

Building now: platform admin, manufacturer, consumer.
Deferred, do not build: printing/QC end, pharmacy end, sale events, offline redemption, AI models, iOS.

## Getting started

1. Read [docs/00-index.md](docs/00-index.md), then [docs/01](docs/01-scope-and-roles.md) and [docs/02](docs/02-architecture.md).
2. Answer the blocking questions in [docs/15](docs/15-open-decisions.md) — especially **what counts as one physical unit**.
3. Run the three Week 0 spikes in [docs/13](docs/13-week-0-spikes.md).
