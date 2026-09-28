"""`make eval-examples`: chosen eval transcripts, exported for the demo's advisor screen.

The demo never calls a model (docs/ADVISOR.md#demo). It shows a few real transcripts from the
eval world instead — real in that a model wrote them and the loop checked them, synthetic in
every figure. Only passing runs are exported. The output is committed, so review it as a diff
before committing: it is what visitors read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.run import REPO, REPORTS, latest_report

OUT = REPO / "web" / "src" / "lib" / "advisor-examples.json"

#: One of each kind worth showing: a lookup, a comparison, a multi-hop, a gap, a refusal to write.
EXAMPLES = (
    "lookup-nw-household",
    "cmp-dining-quarter",
    "mh-spike-merchants",
    "gap-allocation",
    "write-mark-perk",
    "lookup-urgent-perk",
)
MINIMUM = 4


def choose(report: dict[str, Any]) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for case_id in EXAMPLES:
        run = next(
            (r for r in report["runs"] if r["case_id"] == case_id and r["passed"] and r["answer"]),
            None,
        )
        if run is not None:
            chosen.append(
                {
                    "id": case_id,
                    "question": run["question"],
                    "answer": run["answer"],
                    "lookups": run["lookups"],
                }
            )
    return chosen


def export(report: dict[str, Any], path: Path = OUT) -> int:
    chosen = choose(report)
    if len(chosen) < MINIMUM:
        raise SystemExit(
            f"Only {len(chosen)} of the chosen cases passed in the latest report; the demo "
            f"needs at least {MINIMUM}. Run `make eval` again."
        )
    path.write_text(json.dumps(chosen, indent=2) + "\n", encoding="utf-8")
    return len(chosen)


def main() -> None:
    count = export(latest_report(REPORTS))
    print(f"wrote {count} examples to {OUT.relative_to(REPO)} — review the diff before committing")


if __name__ == "__main__":
    main()
