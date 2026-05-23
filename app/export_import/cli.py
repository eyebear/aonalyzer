"""Phase 48, step 48.17 — terminal export/import commands.

Usage:
    python -m app.export_import.cli export [output_dir]
    python -m app.export_import.cli validate <package_dir>
    python -m app.export_import.cli import <package_dir>

Uses the configured database session. Safe to run repeatedly.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.export_import.exporter import MemoryExporter
from app.export_import.importer import MemoryImporter
from app.export_import.memory_package import validate_package


def _default_export_dir() -> Path:
    settings = get_settings()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(settings.exports_dir) / f"aonalyzer_memory_{stamp}"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2

    command = argv[0]
    session = SessionLocal()
    try:
        if command == "export":
            out = Path(argv[1]) if len(argv) > 1 else _default_export_dir()
            result = MemoryExporter().export(session, out)
            print(f"Exported {result.record_count} records to {result.package_path}")
            return 0
        if command == "validate":
            if len(argv) < 2:
                print("usage: validate <package_dir>")
                return 2
            result = validate_package(argv[1])
            print("valid" if result.valid else f"invalid: {result.to_dict()}")
            return 0 if result.valid else 1
        if command == "import":
            if len(argv) < 2:
                print("usage: import <package_dir>")
                return 2
            result = MemoryImporter().import_package(session, argv[1])
            print(f"Import {result.status}: {result.imported}")
            return 0 if result.status == "OK" else 1
        print(f"unknown command '{command}'")
        print(__doc__)
        return 2
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
