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
from app.models.advisor import (
    AdvisorConversation,
    AdvisorMessage,
    AdvisorToolCall,
    AdvisorTurn,
    AdvisorUsage,
)
from app.models.card_perk import CardPerk, PerkRedemption
from app.models.enums import (
    AccountKind,
    AccountSubtype,
    CategoryKind,
    CategorySource,
    DataSource,
    GoalKind,
    GoalStatus,
    MatchType,
    PerkCadence,
    RiskTolerance,
)
from app.models.goal import Goal, GoalAccount
from app.models.liability_terms import LiabilityTerms
from app.models.planning import MemberProfile, PlanningAssumptions
from app.models.system import DataMarker, ImportMapping
from app.models.transaction import CategorizationRule, Category, Transaction
from app.models.user import User

__all__ = [
    "MONEY",
    "Account",
    "AccountKind",
    "AccountSubtype",
    "AdvisorConversation",
    "AdvisorMessage",
    "AdvisorToolCall",
    "AdvisorTurn",
    "AdvisorUsage",
    "BalanceSnapshot",
    "CardPerk",
    "CategorizationRule",
    "Category",
    "CategoryKind",
    "CategorySource",
    "DataMarker",
    "DataSource",
    "Goal",
    "GoalAccount",
    "GoalKind",
    "GoalStatus",
    "ImportMapping",
    "Institution",
    "LiabilityTerms",
    "MatchType",
    "MemberProfile",
    "OwnershipStake",
    "PerkCadence",
    "PerkRedemption",
    "PlanningAssumptions",
    "RiskTolerance",
    "Transaction",
    "User",
]
