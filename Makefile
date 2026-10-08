.PHONY: bootstrap check test baseline dirs

bootstrap:
	pnpm install
	mkdir -p var/transparency secrets

dirs:
	mkdir -p var/transparency secrets

check:
	pnpm check

test:
	pnpm test

baseline:
	./scripts/baseline.sh
