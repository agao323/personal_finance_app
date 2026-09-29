"""`make eval-label`: the owner marks recorded advice answers pass or fail, one at a time.

The advice rubric is a model grading a model, and that needs checking. These labels are the
check: every `make eval` re-grades each labelled answer with the rubric and reports how often
it agreed; below 90% the advice results are marked untrusted.

Answers are synthetic — the eval world's — so the labels file holds no real data. It lives in
`data/evals/labels.json` all the same, beside the reports it came from.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evals.run import ADVICE, LABELS, REPORTS, label_key, latest_report, load_labels


def pending(report: dict[str, Any], labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Advice answers in the report that have no label yet, once each."""
    done = {label_key(label["case_id"], label["answer"]) for label in labels}
    out: list[dict[str, Any]] = []
    for run in report["runs"]:
        if run["category"] not in ADVICE or not run.get("answer"):
            continue
        key = label_key(run["case_id"], run["answer"]["text"])
        if key not in done:
            done.add(key)
            out.append(run)
    return out


def label(
    report: dict[str, Any],
    path: Path = LABELS,
    ask: Callable[[str], str] = input,
    show: Callable[[str], None] = print,
) -> int:
    labels = load_labels(path)
    todo = pending(report, labels)
    if not todo:
        show("No unlabelled advice answers in the latest report.")
        return 0
    added = 0
    for run in todo:
        show(f"\n── {run['case_id']} ──\nQ: {run['question']}\n\n{run['answer']['text']}\n")
        choice = ask("pass / fail / skip / quit: ").strip().lower()
        if choice in {"q", "quit"}:
            break
        if choice not in {"p", "pass", "f", "fail"}:
            continue
        labels.append(
            {
                "case_id": run["case_id"],
                "question": run["question"],
                "answer": run["answer"]["text"],
                "label": "pass" if choice.startswith("p") else "fail",
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")
        added += 1
    show(f"{added} labelled; {len(labels)} in all.")
    return added


def main() -> None:
    label(latest_report(REPORTS))


if __name__ == "__main__":
    main()
