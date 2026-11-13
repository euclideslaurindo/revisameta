# Thin wrapper over scripts/*.sh (ADR-010). On Windows, run the scripts directly in Git Bash.
.PHONY: up up-lite down test test-backend test-stats-r stats-r-lock logs

up:
	docker compose up -d

up-lite:
	docker compose --profile lite up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

test: test-backend test-stats-r

test-backend:
	scripts/test-backend.sh

test-stats-r:
	scripts/test-stats-r.sh

stats-r-lock:
	scripts/stats-r-lock.sh
