"""Clear persisted claim records for the configured lab alias.

This removes Azure Table claim records only. Source evidence under data/claims is preserved.
Use --yes to perform deletion; without it the script only reports what would be removed.
"""
from __future__ import annotations

import argparse
import pathlib

import config as cfg
import store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="delete all records; without this flag the command is a dry run",
    )
    parser.add_argument(
        "--clear-out",
        action="store_true",
        help="also delete generated JSON files from the repository out folder",
    )
    args = parser.parse_args()

    table = store._client(cfg.CLAIM_TABLE)
    records = list(table.list_entities())
    print(f"Claims table: {cfg.CLAIM_TABLE}")
    print(f"Records found: {len(records)}")

    if not args.yes:
        print("Dry run only. Re-run with --yes to delete these records.")
        return 0

    for entity in records:
        table.delete_entity(entity["PartitionKey"], entity["RowKey"])
    print(f"Deleted {len(records)} Azure Table records.")

    if args.clear_out:
        out_dir = pathlib.Path(__file__).resolve().parents[1] / "out"
        output_files = list(out_dir.glob("*.json")) if out_dir.is_dir() else []
        for path in output_files:
            path.unlink()
        print(f"Deleted {len(output_files)} generated output files from {out_dir}.")
    else:
        print("Local out/*.json files were preserved. Use --clear-out to remove them.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
