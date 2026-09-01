"""Module entrypoint so `python -m workflo_worker` works."""

from workflo_worker.main import run_worker


if __name__ == "__main__":
    run_worker()
