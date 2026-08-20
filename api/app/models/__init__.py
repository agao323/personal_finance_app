"""Model package.

Importing this module registers every table on ``Base.metadata``. Alembic's env.py and
the test fixtures rely on that, so a new model file must be imported here or its table
will be missing from autogenerate and from the schema tests.
"""

from app.models.account import (
    MONEY,
    Account,
    BalanceSnapshot,
    Institution,
    OwnershipStake,
)
from app.models.enums import (
    AccountKind,
    AccountSubtype,
    CategoryKind,
    CategorySource,
    DataSource,
    MatchType,
)
from app.models.system import DataMarker, ImportMapping
from app.models.transaction import CategorizationRule, Category, Transaction
from app.models.user import User

__all__ = [
    "MONEY",
    "Account",
    "AccountKind",
    "AccountSubtype",
    "BalanceSnapshot",
    "CategorizationRule",
    "Category",
    "CategoryKind",
    "CategorySource",
    "DataMarker",
    "DataSource",
    "ImportMapping",
    "Institution",
    "MatchType",
    "OwnershipStake",
    "Transaction",
    "User",
]
