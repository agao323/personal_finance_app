#!/usr/bin/env python3
"""Check that the docs are true, reachable and indexed — and generate the plan index.

The docs are the system of record for every agent that works here (AGENTS.md). A doc that
lies is worse than no doc, because it is trusted, so these checks fail the build:

  map          AGENTS.md is at most 100 lines; CLAUDE.md is only `@AGENTS.md`.
  links        Every relative link and #anchor in every .md resolves, and every docs/ or
               tickets/ path cited in code, tests, config or workflows exists.
  reachable    Every file under docs/ is at most two links from AGENTS.md.
  indexes      design-docs/index.md, adr/README.md, product-specs/index.md and
               references/index.md each list every file in their folder.
  plans        Every plan has the required header fields, a valid status in the folder
               that matches it, a unique ID, and Blocked-by IDs that exist.
  plan-index   docs/generated/exec-plans.md matches what the plan headers generate.

Usage:
  scripts/check_docs.py [--root DIR] [CHECK ...]     run the named checks (default: all)
  scripts/check_docs.py --write-plan-index           regenerate docs/generated/exec-plans.md

Standard library only. Never opens anything under data/ — real financial data lives there,
and "never read real values" applies to tools as much as to sessions. Each failure says the
rule, the doc that states it, and how to fix it. Self-tests: scripts/test_guards.sh.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".next",
    "data",  # real financial data: never opened, by rule
    ".claude",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "test-results",
    "playwright-report",
    ".pnpm-store",
    "coverage",
    "htmlcov",
}
CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".sh",
    ".toml",
    ".yml",
    ".yaml",
    ".ini",
    ".cfg",
    ".txt",
    ".example",
}
CODE_NAMES = {"Makefile", "Dockerfile", ".prettierignore", ".gitignore", ".env.example"}
SKIP_FILES = {"pnpm-lock.yaml", "uv.lock", "openapi.json"}

MAX_AGENTS_LINES = 100
MAX_HOPS = 2
ACTIVE_STATUSES = {"todo", "in-progress", "planning"}
COMPLETED_STATUSES = {"done", "closed"}
PLAN_FILE = re.compile(r"^(\d{3}[a-z]?)-[a-z0-9][a-z0-9-]*\.md$")
PLAN_ID = re.compile(r"\b(\d{3}[a-z]?)\b")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


@dataclass
class Problem:
    where: str
    what: str


@dataclass
class Check:
    name: str
    rule: str
    doc: str
    fix: str
    problems: list[Problem] = field(default_factory=list)

    def report(self) -> str:
        lines = [f"check_docs: {self.name} — {len(self.problems)} problem(s)"]
        lines += [f"  {p.where}: {p.what}" for p in self.problems]
        lines += [f"  Rule: {self.rule}", f"  Doc:  {self.doc}", f"  Fix:  {self.fix}"]
        return "\n".join(lines)


# ── markdown parsing ──────────────────────────────────────────────────────────

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
HTML_ID = re.compile(r"""<[a-zA-Z][^>]*?\b(?:id|name)\s*=\s*["']([^"']+)["']""")


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line outside fenced code blocks."""
    out: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            out.append((number, line))
    return out


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: render to text, lowercase, drop punctuation and
    symbols (keeping `-` and `_`), and turn each space into `-`."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # links → their text
    text = re.sub(r"<[^>]+>", "", text)  # inline HTML
    kept = [ch for ch in text.lower() if ch in " -_" or unicodedata.category(ch)[0] in "LMN"]
    return "".join(kept).replace(" ", "-")


def anchors(text: str) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    for _, line in _prose_lines(text):
        match = HEADING.match(line)
        if match:
            base = slug(match.group(2))
            n = counts.get(base, 0)
            counts[base] = n + 1
            found.add(base if n == 0 else f"{base}-{n}")
        found.update(HTML_ID.findall(line))
    return found


def links(text: str) -> list[tuple[int, str]]:
    """(line, target) for every markdown link outside code."""
    out: list[tuple[int, str]] = []
    for number, line in _prose_lines(text):
        for target in LINK.findall(INLINE_CODE.sub("", line)):
            out.append((number, target))
    return out


def _is_external(target: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target)) or target.startswith("//")


# ── repository walking ────────────────────────────────────────────────────────


def _walk(root: Path) -> list[Path]:
    out: list[Path] = []
    stack = [root]
    while stack:
        here = stack.pop()
        for entry in sorted(here.iterdir()):
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                out.append(entry)
    return sorted(out)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


class Docs:
    """Everything the checks need, read once."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files = _walk(root)
        self.markdown = [p for p in self.files if p.suffix == ".md"]
        self._text: dict[Path, str] = {}
        self._anchors: dict[Path, set[str]] = {}

    def text(self, path: Path) -> str:
        if path not in self._text:
            self._text[path] = path.read_text(encoding="utf-8", errors="replace")
        return self._text[path]

    def anchors(self, path: Path) -> set[str]:
        if path not in self._anchors:
            self._anchors[path] = anchors(self.text(path))
        return self._anchors[path]

    def resolve(self, source: Path, target: str) -> tuple[Path | None, str]:
        """A relative link target → (path or None if external/same-file, anchor)."""
        path_part, _, anchor = target.partition("#")
        if not path_part:
            return source, anchor
        return (source.parent / unquote(path_part)).resolve(), anchor

    def outgoing(self, path: Path) -> list[Path]:
        if path.suffix != ".md":
            return []
        out: list[Path] = []
        for _, target in links(self.text(path)):
            if _is_external(target) or target.startswith("#"):
                continue
            resolved, _ = self.resolve(path, target)
            if resolved is not None and resolved.is_file():
                out.append(resolved)
        return out


# ── 1. map ────────────────────────────────────────────────────────────────────


def check_map(docs: Docs) -> Check:
    check = Check(
        "map",
        f"AGENTS.md is the map and stays under {MAX_AGENTS_LINES} lines; CLAUDE.md is only "
        "the line `@AGENTS.md`, so every agent reads one file.",
        "AGENTS.md (top) and docs/PLANS.md",
        "move detail out of AGENTS.md into the doc it belongs in and link it; put nothing in "
        "CLAUDE.md but `@AGENTS.md`.",
    )
    agents = docs.root / "AGENTS.md"
    claude = docs.root / "CLAUDE.md"
    if not agents.is_file():
        check.problems.append(Problem("AGENTS.md", "missing"))
    else:
        count = len(docs.text(agents).splitlines())
        if count > MAX_AGENTS_LINES:
            check.problems.append(
                Problem("AGENTS.md", f"{count} lines, over the limit of {MAX_AGENTS_LINES}")
            )
    if not claude.is_file():
        check.problems.append(Problem("CLAUDE.md", "missing"))
    elif docs.text(claude).strip() != "@AGENTS.md":
        check.problems.append(Problem("CLAUDE.md", "contains more than `@AGENTS.md`"))
    return check


# ── 2. links ──────────────────────────────────────────────────────────────────

CODE_PATH = re.compile(r"((?:docs|tickets)/[A-Za-z0-9_./\[\]-]*[A-Za-z0-9_\]-])(#[A-Za-z0-9_-]+)?")
SHORTHAND = re.compile(r"\b(ARCHITECTURE|SECURITY|PRODUCT)#([a-z0-9_-]+)")
PATH_PRECEDERS = set(" \t\"'`([<=,:")


def _cited_paths(line: str) -> list[tuple[str, str]]:
    """docs/… and tickets/… paths a line of code cites, as (path, anchor)."""
    out: list[tuple[str, str]] = []
    for match in CODE_PATH.finditer(line):
        start = match.start()
        before = line[:start]
        # A path from the repo root, or one reached by ../ — not `dist/docs/`, not `/docs`.
        if before and before[-1] not in PATH_PRECEDERS and not before.endswith("../"):
            continue
        out.append((match.group(1).rstrip("."), (match.group(2) or "")[1:]))
    for match in SHORTHAND.finditer(line):
        out.append((f"docs/{match.group(1)}.md", match.group(2)))
    return out


def _is_code(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return False
    return path.suffix in CODE_SUFFIXES or path.name in CODE_NAMES


def check_links(docs: Docs) -> Check:
    check = Check(
        "links",
        "every relative link and #anchor in every .md resolves, and every docs/ or tickets/ "
        "path cited in code, tests, config or workflows exists — with its anchor.",
        "AGENTS.md#when-docs-and-code-disagree",
        "point the link at where the section lives now (the plan that moved it has a move "
        'map), or restore the heading. A moved heading needs an <a id="old-anchor"></a> '
        "wherever code still cites the old anchor — and some docstrings that cite anchors are "
        "compiled into web/src/lib/api-types.ts, so their anchors must not move.",
    )
    root = docs.root
    for path in docs.markdown:
        for line, target in links(docs.text(path)):
            if _is_external(target):
                continue
            resolved, anchor = docs.resolve(path, target)
            where = f"{_rel(root, path)}:{line}"
            if resolved is None:
                continue
            if not resolved.exists():
                check.problems.append(Problem(where, f"link to missing {target}"))
                continue
            if anchor and resolved.suffix == ".md" and anchor not in docs.anchors(resolved):
                check.problems.append(Problem(where, f"link to missing anchor {target}"))

    for path in docs.files:
        if not _is_code(path):
            continue
        for number, source_line in enumerate(docs.text(path).splitlines(), start=1):
            for cited, cited_anchor in _cited_paths(source_line):
                cited_path = (root / cited).resolve()
                where = f"{_rel(root, path)}:{number}"
                if not cited_path.exists():
                    check.problems.append(Problem(where, f"cites missing {cited}"))
                elif (
                    cited_anchor
                    and cited_path.suffix == ".md"
                    and cited_anchor not in docs.anchors(cited_path)
                ):
                    check.problems.append(
                        Problem(where, f"cites missing anchor {cited}#{cited_anchor}")
                    )
    return check


# ── 3. reachable ──────────────────────────────────────────────────────────────


def check_reachable(docs: Docs) -> Check:
    check = Check(
        "reachable",
        f"every file under docs/ is at most {MAX_HOPS} links from AGENTS.md, so an agent "
        "starting from the map can find it.",
        "AGENTS.md#where-to-look",
        "link the file from the index for its folder (design-docs/index.md, "
        "product-specs/index.md, references/index.md, adr/README.md), from RELIABILITY.md for "
        "a runbook, or from AGENTS.md itself. Plans are reached through "
        "docs/generated/exec-plans.md — run `make docs`.",
    )
    root = docs.root
    start = (root / "AGENTS.md").resolve()
    if not start.is_file():
        check.problems.append(Problem("AGENTS.md", "missing, so nothing is reachable"))
        return check
    hops = {start: 0}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        for nxt in docs.outgoing(here):
            if nxt not in hops:
                hops[nxt] = hops[here] + 1
                queue.append(nxt)
    docs_dir = root / "docs"
    for path in docs.files:
        if docs_dir not in path.parents or path.name == ".DS_Store":
            continue
        distance = hops.get(path.resolve())
        rel = _rel(root, path)
        if distance is None:
            check.problems.append(Problem(rel, "not linked from anywhere reachable (orphan)"))
        elif distance > MAX_HOPS:
            check.problems.append(Problem(rel, f"{distance} links from AGENTS.md"))
    return check


# ── 4. indexes ────────────────────────────────────────────────────────────────


def _index_rows(docs: Docs, index: Path) -> dict[Path, str]:
    """Each linked file → the line that links it, preferring a table row over prose.

    An index often names a file in its introduction before its table does; the status and
    date live in the row.
    """
    lines = docs.text(index).splitlines()
    rows: dict[Path, str] = {}
    for number, target in links(docs.text(index)):
        if _is_external(target) or target.startswith("#"):
            continue
        resolved, _ = docs.resolve(index, target)
        if resolved is None:
            continue
        line = lines[number - 1]
        current = rows.get(resolved)
        if current is None or (
            line.lstrip().startswith("|") and not current.lstrip().startswith("|")
        ):
            rows[resolved] = line
    return rows


def check_indexes(docs: Docs) -> Check:
    check = Check(
        "indexes",
        "each folder's index lists every file in it: design-docs/index.md (design docs, "
        "every ADR, DECISIONS.md — each with a status of current or superseded and a "
        "last-verified date), adr/README.md, product-specs/index.md, references/index.md.",
        "docs/design-docs/index.md",
        "add a row for the new file to its folder's index. In design-docs/index.md the row "
        "needs a status (current | superseded) and the date its claims were last checked "
        "against the code.",
    )
    root = docs.root
    d = root / "docs"

    def folder(name: str, *exclude: str) -> list[Path]:
        base = d / name
        if not base.is_dir():
            return []
        return sorted(
            p.resolve()
            for p in base.iterdir()
            if p.is_file() and p.name not in exclude and p.name != ".DS_Store"
        )

    design_index = d / "design-docs" / "index.md"
    if design_index.is_file():
        rows = _index_rows(docs, design_index)
        expected = [
            *folder("design-docs", "index.md"),
            *folder("adr", "README.md"),
            *([(d / "DECISIONS.md").resolve()] if (d / "DECISIONS.md").is_file() else []),
        ]
        for path in expected:
            where = _rel(root, design_index)
            row = rows.get(path)
            if row is None:
                check.problems.append(Problem(where, f"does not list {_rel(root, path)}"))
                continue
            if not re.search(r"\b(current|superseded)\b", row):
                check.problems.append(
                    Problem(where, f"row for {_rel(root, path)} has no status (current|superseded)")
                )
            if not DATE.search(row):
                check.problems.append(
                    Problem(where, f"row for {_rel(root, path)} has no last-verified date")
                )
    elif (d / "design-docs").is_dir():
        check.problems.append(Problem("docs/design-docs/index.md", "missing"))

    adr_readme = d / "adr" / "README.md"
    if adr_readme.is_file():
        text = docs.text(adr_readme)
        for path in folder("adr", "README.md"):
            if path.name not in text:
                check.problems.append(Problem(_rel(root, adr_readme), f"does not list {path.name}"))

    for name in ("product-specs", "references"):
        index = d / name / "index.md"
        if not (d / name).is_dir():
            continue
        if not index.is_file():
            check.problems.append(Problem(f"docs/{name}/index.md", "missing"))
            continue
        rows = _index_rows(docs, index)
        for path in folder(name, "index.md"):
            if path not in rows:
                check.problems.append(Problem(_rel(root, index), f"does not link {path.name}"))
    return check


# ── 5. plans ──────────────────────────────────────────────────────────────────


@dataclass
class Plan:
    path: Path
    folder: str
    id: str
    title: str
    fields: dict[str, str]

    @property
    def status(self) -> str:
        return self.fields.get("Status", "")

    @property
    def status_word(self) -> str:
        return self.status.split()[0] if self.status else ""

    def ids(self, name: str) -> list[str]:
        return PLAN_ID.findall(self.fields.get(name, ""))


HEADER_FIELD = re.compile(r"^(Status|Wave|Lane|Blocked by|Integrates with|Read first):\s*(.*)$")


def parse_plan(path: Path, folder: str, text: str) -> Plan:
    lines = text.splitlines()
    first = lines[0] if lines else ""
    title_match = re.match(r"^#\s+(\d{3}[a-z]?)\s+—\s+(.+)$", first)
    fields: dict[str, str] = {}
    for line in lines[1:12]:
        if line.startswith("## "):
            break
        # "Wave: 7   Lane: —" carries two fields on one line.
        for part in re.split(r"\s{2,}(?=Lane:)", line):
            match = HEADER_FIELD.match(part.strip())
            if match:
                fields[match.group(1)] = match.group(2).strip()
    file_match = PLAN_FILE.match(path.name)
    return Plan(
        path=path,
        folder=folder,
        id=(file_match.group(1) if file_match else ""),
        title=(title_match.group(2) if title_match else ""),
        fields=fields | ({"_title_id": title_match.group(1)} if title_match else {}),
    )


def load_plans(docs: Docs) -> list[Plan]:
    plans: list[Plan] = []
    for folder in ("active", "completed"):
        base = docs.root / "docs" / "exec-plans" / folder
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            plans.append(parse_plan(path, folder, docs.text(path)))
    return plans


def _id_key(plan_id: str) -> tuple[int, str]:
    return int(plan_id[:3]), plan_id[3:]


def check_plans(docs: Docs) -> Check:
    check = Check(
        "plans",
        "every plan in docs/exec-plans/ is named NNN-slug.md, starts `# NNN — Title`, and "
        "has Status, Wave, Lane and Blocked by; Status is todo | in-progress | planning "
        "(in active/) or done | closed (in completed/); IDs are unique; Blocked-by and "
        "Integrates-with IDs exist; active plans have Read first, and every Read first path "
        "exists.",
        "docs/PLANS.md#plan-format",
        "fix the header to match the format in docs/PLANS.md. When a plan's status changes, "
        "`git mv` it to the matching folder and run `make docs`.",
    )
    root = docs.root
    leftovers = sorted((root / "tickets").glob("[0-9]*.md")) if (root / "tickets").is_dir() else []
    for path in leftovers:
        check.problems.append(
            Problem(_rel(root, path), "a plan outside docs/exec-plans/ — move it there")
        )

    plans = load_plans(docs)
    known = {plan.id for plan in plans}
    seen: dict[str, str] = {}
    for plan in plans:
        rel = _rel(root, plan.path)
        if not plan.id:
            check.problems.append(Problem(rel, "filename is not NNN-slug.md"))
            continue
        if plan.id in seen:
            check.problems.append(Problem(rel, f"duplicate ID {plan.id} (also {seen[plan.id]})"))
        seen.setdefault(plan.id, rel)
        if plan.fields.get("_title_id") != plan.id:
            check.problems.append(Problem(rel, f"first line is not `# {plan.id} — Title`"))
        for name in ("Status", "Wave", "Lane", "Blocked by"):
            if name not in plan.fields:
                check.problems.append(Problem(rel, f"missing `{name}:`"))
        word = plan.status_word
        if word and word not in ACTIVE_STATUSES | COMPLETED_STATUSES:
            check.problems.append(Problem(rel, f"unknown status `{word}`"))
        elif word:
            wanted = "active" if word in ACTIVE_STATUSES else "completed"
            if plan.folder != wanted:
                check.problems.append(
                    Problem(rel, f"status `{word}` belongs in exec-plans/{wanted}/")
                )
        for name in ("Blocked by", "Integrates with"):
            for other in plan.ids(name):
                if other not in known:
                    check.problems.append(Problem(rel, f"{name} names {other}, which has no plan"))
        read_first = plan.fields.get("Read first")
        if read_first is None:
            if plan.folder == "active":
                check.problems.append(Problem(rel, "active plan has no `Read first:`"))
            continue
        for entry in (e.strip() for e in read_first.split(",")):
            if not entry or entry.lower() == "none" or ("/" not in entry and "." not in entry):
                continue
            cited, _, anchor = entry.split()[0].partition("#")
            target = (root / cited).resolve()
            if not target.exists():
                check.problems.append(Problem(rel, f"Read first names missing {cited}"))
            elif anchor and target.suffix == ".md" and anchor not in docs.anchors(target):
                check.problems.append(Problem(rel, f"Read first names missing anchor {entry}"))
    return check


# ── 6. the generated plan index ───────────────────────────────────────────────

PLAN_INDEX = Path("docs") / "generated" / "exec-plans.md"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").strip()


def render_plan_index(docs: Docs) -> str:
    plans = sorted(load_plans(docs), key=lambda p: _id_key(p.id) if p.id else (0, ""))
    plans = [p for p in plans if p.id]
    active = [p for p in plans if p.folder == "active"]
    completed = [p for p in plans if p.folder == "completed"]
    numbers = sorted({int(p.id[:3]) for p in plans})
    gaps = (
        [f"{n:03d}" for n in range(numbers[0], numbers[-1] + 1) if n not in numbers]
        if numbers
        else []
    )
    waves = sorted({p.fields.get("Wave", "") for p in plans} - {""}, key=lambda w: (len(w), w))

    out = [
        "# Plans",
        "",
        "<!-- Generated by `make docs` from the plan headers in docs/exec-plans/. Do not edit: "
        "change a plan's header and run `make docs`; `make test` fails on drift. -->",
        "",
        "Every plan, generated from its header. How to work one: [PLANS.md](../PLANS.md). "
        "Known debt that is not a plan: "
        "[tech-debt-tracker.md](../exec-plans/tech-debt-tracker.md).",
        "",
        f"{len(plans)} plans: {len(active)} active, {len(completed)} completed, in waves "
        f"{', '.join(waves)}." + (f" No plan file for: {', '.join(gaps)}." if gaps else ""),
        "",
        "## Active",
        "",
        "| ID | Plan | Status | Wave | Lane | Blocked by |",
        "|---|---|---|---|---|---|",
    ]
    for plan in active:
        link = f"[{_cell(plan.title)}](../exec-plans/active/{plan.path.name})"
        out.append(
            f"| {plan.id} | {link} | {_cell(plan.status)} | {_cell(plan.fields.get('Wave', ''))} "
            f"| {_cell(plan.fields.get('Lane', ''))} | {_cell(plan.fields.get('Blocked by', ''))} |"
        )
    out += ["", "## Completed", "", "| ID | Plan | Status | Wave |", "|---|---|---|---|"]
    for plan in completed:
        link = f"[{_cell(plan.title)}](../exec-plans/completed/{plan.path.name})"
        out.append(
            f"| {plan.id} | {link} | {_cell(plan.status)} | {_cell(plan.fields.get('Wave', ''))} |"
        )
    return "\n".join(out) + "\n"


def check_plan_index(docs: Docs) -> Check:
    check = Check(
        "plan-index",
        "docs/generated/exec-plans.md is generated from the plan headers and never hand-edited.",
        "docs/PLANS.md#how-to-work-a-plan",
        "run `make docs` and commit docs/generated/exec-plans.md with the plan change.",
    )
    path = docs.root / PLAN_INDEX
    if not (docs.root / "docs" / "exec-plans").is_dir():
        return check
    expected = render_plan_index(docs)
    if not path.is_file():
        check.problems.append(Problem(PLAN_INDEX.as_posix(), "missing"))
    elif docs.text(path) != expected:
        check.problems.append(Problem(PLAN_INDEX.as_posix(), "out of date with the plan headers"))
    return check


# ── main ──────────────────────────────────────────────────────────────────────

CHECKS = {
    "map": check_map,
    "links": check_links,
    "reachable": check_reachable,
    "indexes": check_indexes,
    "plans": check_plans,
    "plan-index": check_plan_index,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--write-plan-index", action="store_true")
    parser.add_argument("checks", nargs="*", metavar="CHECK", help=", ".join(CHECKS))
    args = parser.parse_args(argv)

    unknown = [name for name in args.checks if name not in CHECKS]
    if unknown:
        print(
            f"check_docs: unknown check(s) {unknown}; choose from {list(CHECKS)}", file=sys.stderr
        )
        return 2
    root: Path = args.root.resolve()
    if not root.is_dir():
        print(f"check_docs: no such directory: {root}", file=sys.stderr)
        return 2

    docs = Docs(root)
    if args.write_plan_index:
        target = root / PLAN_INDEX
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_plan_index(docs), encoding="utf-8")
        print(f"wrote {PLAN_INDEX.as_posix()}")
        return 0

    names = args.checks or list(CHECKS)
    failed = [check for check in (CHECKS[name](docs) for name in names) if check.problems]
    if failed:
        print("\n\n".join(check.report() for check in failed), file=sys.stderr)
        return 1
    print(f"check_docs: ok ({', '.join(names)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
