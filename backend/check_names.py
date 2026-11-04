"""Run pyflakes on the crawler, worker, and extractor modules."""
from io import StringIO
from pathlib import Path

from pyflakes import api
from pyflakes.reporter import Reporter


BACKEND_DIR = Path(__file__).resolve().parent
APP_DIR = BACKEND_DIR / "app"
TARGETS = [APP_DIR / "crawler.py", APP_DIR / "worker.py"]
TARGETS.extend(
    path
    for path in sorted(APP_DIR.rglob("*.py"))
    if "extract" in path.stem.lower() and path not in TARGETS
)


def main():
    total = 0
    for path in TARGETS:
        stdout = StringIO()
        stderr = StringIO()
        reporter = Reporter(stdout, stderr)
        api.checkPath(str(path), reporter)
        messages = [
            line for line in (stdout.getvalue() + stderr.getvalue()).splitlines()
            if "imported but unused" not in line
        ]
        for message in messages:
            print(message)
        total += len(messages)
    if not total:
        print("No pyflakes findings (unused imports filtered).")


if __name__ == "__main__":
    main()
