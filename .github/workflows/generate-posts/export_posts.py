#!/usr/bin/env python3
"""
Export Hugo content list to Databricks-friendly format (JSON Lines).

Uses only the output of `hugo list all` (CSV) as the source of truth so the
export stays compatible with Hugo's data model. No packages required (stdlib only).
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone


def content_type_from_path(path: str) -> str:
    """Derive content type from Hugo path (content/...)."""
    if not path:
        return "other"
    normalized = path.strip().lower().replace("\\", "/")
    if "/blog/" in normalized:
        return "blog"
    if "/pages/" in normalized:
        return "page"
    if "/prompts/" in normalized:
        return "prompt"
    return "other"


def safe_bool(val: str) -> bool:
    """Parse CSV draft column (true/false string)."""
    if val is None:
        return False
    return str(val).strip().lower() in ("true", "1", "yes")


def row_to_record(row: dict, export_ts: str) -> dict:
    """Turn one CSV row from hugo list all into one export record with derived fields."""
    path = row.get("path", "").strip()
    record = {
        "path": path,
        "slug": (row.get("slug") or "").strip(),
        "title": (row.get("title") or "").strip(),
        "date": (row.get("date") or "").strip(),
        "expiryDate": (row.get("expiryDate") or "").strip(),
        "publishDate": (row.get("publishDate") or "").strip(),
        "draft": safe_bool(row.get("draft", "")),
        "permalink": (row.get("permalink") or "").strip(),
        "kind": (row.get("kind") or "").strip(),
        "section": (row.get("section") or "").strip(),
        "content_type": content_type_from_path(path),
        "export_timestamp": export_ts,
    }
    return record


def main() -> int:
    export_ts = datetime.now(timezone.utc).isoformat()
    list_file = os.environ.get("HUGO_LIST_FILE", "").strip()
    out_file = os.environ.get("OUTPUT_FILE", "posts_export.jsonl").strip()

    if not list_file or not os.path.isfile(list_file):
        print("HUGO_LIST_FILE must point to a CSV file from 'hugo list all'.", file=sys.stderr)
        return 1

    records = []
    with open(list_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row_to_record(row, export_ts))

    with open(out_file, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Exported {len(records)} records to {out_file}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
