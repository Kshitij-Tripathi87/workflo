.PHONY: bootstrap check test baseline dirs python-install python-test

bootstrap:
	pnpm install
	mkdir -p var/transparency secrets

dirs:
	mkdir -p var/transparency secrets

check:
	pnpm check

test:
	pnpm test

# The Python half of the repository is ~20 separate setuptools projects, not a
# single workspace. Without this step every suite fails with ModuleNotFoundError
# and looks like a code defect. See scripts/python-env.sh.
python-install:
	./scripts/python-env.sh install

python-test:
	./scripts/python-env.sh test

baseline:
	./scripts/baseline.sh
