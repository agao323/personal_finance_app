"""The layer rules in docs/ARCHITECTURE.md#layers, checked mechanically.

    models ──► schemas ──► services ──► routers ──► main.py

Each rule below is a statement from the architecture doc, a scan of the source with the
standard library's ``ast``, and a failure message written for whoever reads CI output: the
rule, the file and line, the doc, and how to fix it. Imports inside functions count.

Existing violations live in ``ALLOWLIST``, and **the allowlist may only shrink**: each entry
cites a tech-debt item that must exist, an entry that no longer matches a violation fails
(so fixing the code forces deleting the entry), and its size must equal
``ALLOWLIST_CEILING`` (so growing it takes two deliberate edits in one diff).

The second half of the file runs every rule against fixture trees that break it. A guard
that never fires looks exactly like one that is broken.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.conftest import API_ROOT

REPO_ROOT = API_ROOT.parent
TRACKER = REPO_ROOT / "docs" / "exec-plans" / "tech-debt-tracker.md"
DOC = "docs/ARCHITECTURE.md#layers"


@dataclass(frozen=True)
class Rule:
    id: str
    statement: str
    fix: str
    doc: str = DOC


@dataclass(frozen=True)
class Violation:
    rule: Rule
    path: str  # relative to the api root, e.g. "app/routers/cards.py"
    line: int
    detail: str

    def report(self) -> str:
        return (
            f"Architecture rule broken: {self.rule.id}\n"
            f"  {self.path}:{self.line}  {self.detail}\n"
            f"  Rule: {self.rule.statement}\n"
            f"  Doc:  {self.rule.doc}\n"
            f"  Fix:  {self.rule.fix}"
        )


SERVICES_ARE_HTTP_FREE = Rule(
    "services-are-http-free",
    "services never import routers, deps, main, or fastapi/starlette — a service must be "
    "callable from a script, a test or a connector with no HTTP in sight.",
    "raise a domain exception (like ownership.OverlappingStakeError) and translate it to an "
    "HTTPException in the router that called the service.",
)
MODELS_ARE_LEAVES = Rule(
    "models-are-leaves",
    "models never import services, schemas, routers, deps or main; they see only db.Base "
    "and other models.",
    "move the logic into a service that imports the model, or the enum into models/enums.py.",
)
SCHEMAS_DESCRIBE = Rule(
    "schemas-describe-not-do",
    "schemas never import services, routers, deps or main; they may use models.enums and "
    "other schemas.",
    "compute the value in a service and pass it into the schema from the router.",
)
ROUTERS_ARE_SIBLINGS = Rule(
    "routers-do-not-import-routers",
    "a router never imports another router (private helpers named routers/_*.py excepted).",
    "move the shared logic into a service that both routers call.",
)
OWNERSHIP_IN_ONE_PLACE = Rule(
    "ownership-is-applied-in-one-place",
    "ownership percentages are applied only in services/ownership.py: no multiplication or "
    "division involving a percentage or stake anywhere else.",
    "call services.ownership.adjust(amount, percentage) — the only place a stake is applied "
    "and ownership-adjusted money is rounded.",
    "docs/design-docs/ownership-and-rounding.md#ownership-is-applied-in-exactly-one-place",
)
ROUTERS_DO_NOT_BUILD_SQL = Rule(
    "routers-do-not-build-sql",
    "routers do not import SQLAlchemy query constructs (select, insert, update, delete, func, "
    "text, Table, loader options …); only sqlalchemy.orm.Session, for annotations.",
    "put the query in a service function that takes the session, and call it from the "
    "router. If that removes the last query from an allowlisted router, delete its "
    "ALLOWLIST entry and lower ALLOWLIST_CEILING in the same commit.",
)

RULES = (
    SERVICES_ARE_HTTP_FREE,
    MODELS_ARE_LEAVES,
    SCHEMAS_DESCRIBE,
    ROUTERS_ARE_SIBLINGS,
    OWNERSHIP_IN_ONE_PLACE,
    ROUTERS_DO_NOT_BUILD_SQL,
)

#: Layer (the package under app/) → the rule that constrains its imports, and the module
#: prefixes it must not import.
IMPORT_RULES: dict[str, tuple[Rule, tuple[str, ...]]] = {
    "services": (
        SERVICES_ARE_HTTP_FREE,
        ("fastapi", "starlette", "app.routers", "app.deps", "app.main"),
    ),
    "models": (
        MODELS_ARE_LEAVES,
        ("app.services", "app.schemas", "app.routers", "app.deps", "app.main"),
    ),
    "schemas": (SCHEMAS_DESCRIBE, ("app.services", "app.routers", "app.deps", "app.main")),
    "routers": (ROUTERS_ARE_SIBLINGS, ("app.routers",)),
}

#: A name that holds an ownership share. Deliberately not `bps` or `percent`: converting
#: basis points on the wire (schemas/common.py) is a unit change, not applying a stake.
STAKE_NAME = re.compile(r"percentage|stake", re.IGNORECASE)

#: Existing violations, each tied to a tech-debt item. May only shrink.
ALLOWLIST: dict[tuple[str, str], str] = {
    (ROUTERS_DO_NOT_BUILD_SQL.id, "app/routers/accounts.py"): "TD-001",
    (ROUTERS_DO_NOT_BUILD_SQL.id, "app/routers/cards.py"): "TD-001",
    (ROUTERS_DO_NOT_BUILD_SQL.id, "app/routers/categories.py"): "TD-001",
    (ROUTERS_DO_NOT_BUILD_SQL.id, "app/routers/export.py"): "TD-001",
    (ROUTERS_DO_NOT_BUILD_SQL.id, "app/routers/import_csv.py"): "TD-001",
    (ROUTERS_DO_NOT_BUILD_SQL.id, "app/routers/rules.py"): "TD-001",
    (ROUTERS_DO_NOT_BUILD_SQL.id, "app/routers/transactions.py"): "TD-001",
    (ROUTERS_DO_NOT_BUILD_SQL.id, "app/routers/users.py"): "TD-001",
}
ALLOWLIST_CEILING = 8


# ── the scanner ───────────────────────────────────────────────────────────────


def _python_files(root: Path, *parts: str) -> Iterator[Path]:
    base = root.joinpath(*parts)
    if base.is_dir():
        yield from sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _module_of(api_root: Path, path: Path) -> str:
    return ".".join(path.relative_to(api_root).with_suffix("").parts)


def _imports(tree: ast.AST, module: str) -> Iterator[tuple[int, str, list[str]]]:
    """Every import in the file as (line, module, names), relative imports resolved."""
    package = module.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, []
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:
                base = package.split(".")
                base = base[: len(base) - node.level + 1]
                target = ".".join([*base, target] if target else base)
            yield node.lineno, target, [alias.name for alias in node.names]


def _matches(candidate: str, prefixes: tuple[str, ...]) -> bool:
    return any(candidate == p or candidate.startswith(p + ".") for p in prefixes)


def _is_private_helper(candidate: str) -> bool:
    """`app.routers._stub` and anything inside it: a shared helper, not a router."""
    parts = candidate.split(".")
    return len(parts) > 2 and parts[2].startswith("_")


def _names_a_stake(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and STAKE_NAME.search(child.id):
            return True
        if isinstance(child, ast.Attribute) and STAKE_NAME.search(child.attr):
            return True
    return False


def scan(api_root: Path) -> list[Violation]:
    """Every rule violation under `api_root`/app (and `api_root`/scripts for ownership)."""
    violations: list[Violation] = []

    for path in _python_files(api_root, "app"):
        rel = path.relative_to(api_root).as_posix()
        module = _module_of(api_root, path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        parts = rel.split("/")
        layer = parts[1] if len(parts) > 2 else ""

        if layer in IMPORT_RULES:
            rule, forbidden = IMPORT_RULES[layer]
            for line, target, names in _imports(tree, module):
                candidates = [target, *(f"{target}.{name}" for name in names)]
                for candidate in candidates:
                    if not _matches(candidate, forbidden):
                        continue
                    if rule is ROUTERS_ARE_SIBLINGS and (
                        candidate == "app.routers" or _is_private_helper(candidate)
                    ):
                        continue
                    violations.append(Violation(rule, rel, line, f"imports {candidate}"))
                    break

        if layer == "routers":
            for line, target, names in _imports(tree, module):
                if not _matches(target, ("sqlalchemy",)):
                    continue
                if target == "sqlalchemy.orm" and set(names) <= {"Session"}:
                    continue
                shown = f"from {target} import {', '.join(names)}" if names else f"import {target}"
                violations.append(Violation(ROUTERS_DO_NOT_BUILD_SQL, rel, line, shown))

    for path in [*_python_files(api_root, "app"), *_python_files(api_root, "scripts")]:
        rel = path.relative_to(api_root).as_posix()
        if rel == "app/services/ownership.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            operands: list[ast.AST] = []
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult | ast.Div):
                operands = [node.left, node.right]
            elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Mult | ast.Div):
                operands = [node.target, node.value]
            if not isinstance(node, ast.expr | ast.stmt):
                continue
            if any(_names_a_stake(operand) for operand in operands):
                violations.append(
                    Violation(
                        OWNERSHIP_IN_ONE_PLACE,
                        rel,
                        node.lineno,
                        f"arithmetic on a stake: {ast.unparse(node)[:80]}",
                    )
                )

    return violations


def _unallowed(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if (v.rule.id, v.path) not in ALLOWLIST]


# ── the rules hold for this codebase ──────────────────────────────────────────


def test_the_layer_rules_hold() -> None:
    broken = _unallowed(scan(API_ROOT))
    assert not broken, "\n\n".join(v.report() for v in broken)


def test_every_allowlist_entry_is_still_a_violation() -> None:
    """Fixing the code must delete the entry — that is what makes the list shrink-only."""
    found = {(v.rule.id, v.path) for v in scan(API_ROOT)}
    stale = sorted(set(ALLOWLIST) - found)
    assert not stale, (
        f"allowlist entries with no matching violation: {stale}. The code no longer breaks "
        "the rule — delete these entries from ALLOWLIST in tests/test_architecture.py and "
        f"lower ALLOWLIST_CEILING to match. The allowlist may only shrink ({DOC})."
    )


def test_the_allowlist_only_shrinks() -> None:
    assert len(ALLOWLIST) == ALLOWLIST_CEILING, (
        f"ALLOWLIST has {len(ALLOWLIST)} entries but ALLOWLIST_CEILING is "
        f"{ALLOWLIST_CEILING}. If you removed entries, lower the ceiling to match. If you "
        "added one, don't: fix the code so it follows the rule instead."
    )


def test_every_allowlist_entry_cites_a_real_debt_item() -> None:
    tracked = set(re.findall(r"^### (TD-\d{3})\b", TRACKER.read_text(encoding="utf-8"), re.M))
    cited = set(ALLOWLIST.values())
    assert cited <= tracked, (
        f"allowlist cites {sorted(cited - tracked)}, missing from "
        "docs/exec-plans/tech-debt-tracker.md. Every exception is debt with a written reason."
    )


# ── every rule fires (self-tests) ─────────────────────────────────────────────


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, source in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return tmp_path


def _rules_broken(tmp_path: Path, files: dict[str, str]) -> set[str]:
    return {v.rule.id for v in scan(_tree(tmp_path, files))}


@pytest.mark.parametrize(
    ("rel", "source", "rule"),
    [
        ("app/services/x.py", "from fastapi import HTTPException\n", SERVICES_ARE_HTTP_FREE),
        ("app/services/x.py", "import starlette.requests\n", SERVICES_ARE_HTTP_FREE),
        ("app/services/x.py", "from app.routers import cards\n", SERVICES_ARE_HTTP_FREE),
        ("app/services/x.py", "from app.deps import DbSession\n", SERVICES_ARE_HTTP_FREE),
        ("app/models/x.py", "from app.services import perks\n", MODELS_ARE_LEAVES),
        ("app/models/x.py", "from app.schemas.common import Cents\n", MODELS_ARE_LEAVES),
        ("app/models/x.py", "import app.routers.cards\n", MODELS_ARE_LEAVES),
        ("app/schemas/x.py", "from app.services.perks import MONTHS\n", SCHEMAS_DESCRIBE),
        ("app/routers/x.py", "from app.routers.cards import list_cards\n", ROUTERS_ARE_SIBLINGS),
        ("app/routers/x.py", "from app.routers import cards\n", ROUTERS_ARE_SIBLINGS),
        ("app/routers/x.py", "from . import cards\n", ROUTERS_ARE_SIBLINGS),
        ("app/routers/x.py", "from sqlalchemy import select\n", ROUTERS_DO_NOT_BUILD_SQL),
        ("app/routers/x.py", "from sqlalchemy.orm import joinedload\n", ROUTERS_DO_NOT_BUILD_SQL),
        ("app/routers/x.py", "import sqlalchemy\n", ROUTERS_DO_NOT_BUILD_SQL),
        ("app/services/x.py", "def f(b, stake):\n    return b * stake\n", OWNERSHIP_IN_ONE_PLACE),
        (
            "app/services/x.py",
            "def f(b, row):\n    return b * row.percentage / 100\n",
            OWNERSHIP_IN_ONE_PLACE,
        ),
        ("app/routers/x.py", "def f(b, p):\n    b *= p.percentage\n", OWNERSHIP_IN_ONE_PLACE),
        ("scripts/x.py", "def f(b, s):\n    return b * s.stake\n", OWNERSHIP_IN_ONE_PLACE),
    ],
)
def test_each_rule_catches_a_violation(tmp_path: Path, rel: str, source: str, rule: Rule) -> None:
    assert rule.id in _rules_broken(tmp_path, {rel: source})


def test_an_import_inside_a_function_is_seen(tmp_path: Path) -> None:
    source = "def handler():\n    from fastapi import HTTPException\n    raise HTTPException(400)\n"
    assert SERVICES_ARE_HTTP_FREE.id in _rules_broken(tmp_path, {"app/services/x.py": source})


@pytest.mark.parametrize(
    ("rel", "source"),
    [
        (
            "app/services/x.py",
            "from app.models.account import Account\nfrom sqlalchemy import select\n",
        ),
        ("app/services/x.py", "from app.schemas.import_csv import ColumnMapping\n"),
        (
            "app/services/ownership.py",
            "def adjust(amount, percentage):\n    return amount * percentage\n",
        ),
        ("app/schemas/x.py", "from app.models.enums import AccountKind\n"),
        ("app/schemas/x.py", "def from_bps(bps):\n    return bps / BPS_PER_PERCENT\n"),
        (
            "app/routers/x.py",
            "from sqlalchemy.orm import Session\nfrom app.services import perks\n",
        ),
        ("app/routers/x.py", "from app.routers._stub import not_implemented\n"),
        (
            "app/services/x.py",
            "def f(total, row):\n    total += row.percentage\n    return total\n",
        ),
    ],
)
def test_what_the_layers_allow_passes(tmp_path: Path, rel: str, source: str) -> None:
    assert _rules_broken(tmp_path, {rel: source}) == set()


def test_a_failure_names_the_rule_the_line_the_doc_and_the_fix(tmp_path: Path) -> None:
    [violation] = scan(_tree(tmp_path, {"app/services/x.py": "\n\nimport fastapi\n"}))
    report = violation.report()

    assert "services-are-http-free" in report
    assert "app/services/x.py:3" in report
    assert "Doc:  docs/ARCHITECTURE.md#layers" in report
    assert "Fix:  raise a domain exception" in report


def test_every_rule_has_a_statement_a_doc_and_a_fix() -> None:
    for rule in RULES:
        assert rule.statement and rule.fix and rule.doc.startswith("docs/"), rule.id
