#!/usr/bin/env python3
"""
Analyze DuckDB audit_log to list (thought, code) pairs and optionally export rules for the task translator.
Run from repo root: uv run python scripts/analyze_audit_log.py [--export rules.json]
"""
import json
import os
import sys
from pathlib import Path

# Repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv()

import duckdb

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "universal_tasker.duckdb"


def main():
    export_path = None
    if "--export" in sys.argv:
        i = sys.argv.index("--export")
        if i + 1 < len(sys.argv):
            export_path = Path(sys.argv[i + 1])
        else:
            export_path = DATA_DIR / "task_translator_rules.json"

    if not DB_PATH.exists():
        print(f"No DB at {DB_PATH}. Run the app and complete some tasks first.")
        return 1

    con = duckdb.connect(str(DB_PATH))

    # Schema reminder
    print("--- audit_log columns ---")
    try:
        cols = con.execute("DESCRIBE audit_log").fetchall()
        for c in cols:
            print(" ", c[0], c[1])
    except Exception as e:
        print(" ", e)

    # Distinct (thought, code) with outcome and count
    print("\n--- (thought, code) pairs from audit_log (code not empty) ---")
    rows = con.execute("""
        SELECT thought, code, outcome, COUNT(*) AS n
        FROM audit_log
        WHERE code IS NOT NULL AND TRIM(code) != '' AND LOWER(TRIM(code)) != 'pass'
        GROUP BY thought, code, outcome
        ORDER BY n DESC, thought
    """).fetchall()

    if not rows:
        print("No rows. Run tasks so audit_log has thought/code data.")
        con.close()
        return 0

    seen_thought = set()
    rules_to_export = []

    for thought, code, outcome, n in rows:
        thought_preview = (thought or "")[:80] + ("..." if (thought and len(thought) > 80) else "")
        code_preview = (code or "")[:60] + ("..." if (code and len(code) > 60) else "")
        print(f"  n={n} outcome={outcome}")
        print(f"    thought: {thought_preview}")
        print(f"    code:    {code_preview}")
        print()

        # Build a rule: use first 50 chars of thought as pattern for export
        if export_path and thought and code and thought not in seen_thought:
            seen_thought.add(thought)
            pattern = thought.strip()[:80].lower()
            if pattern:
                rules_to_export.append({
                    "patterns": [pattern],
                    "code": code.strip(),
                })

    con.close()

    if export_path and rules_to_export:
        # Merge with existing rules if file exists
        existing = []
        if export_path.exists():
            try:
                raw = json.loads(export_path.read_text(encoding="utf-8"))
                existing = raw if isinstance(raw, list) else raw.get("rules", [])
            except Exception:
                pass
        # Dedupe by pattern set
        existing_patterns = set()
        for r in existing:
            key = tuple(sorted(r.get("patterns", [])))
            existing_patterns.add(key)
        for r in rules_to_export:
            key = tuple(sorted(r.get("patterns", [])))
            if key not in existing_patterns:
                existing.append(r)
                existing_patterns.add(key)
        export_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Exported {len(rules_to_export)} new rules to {export_path} (total {len(existing)} rules).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
