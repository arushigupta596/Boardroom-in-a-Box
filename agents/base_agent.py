"""
Base Agent Class
================
Common functionality for all boardroom agents.
Includes SQL guardrails for defense-in-depth security.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal
from datetime import date, datetime
import os

from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence, validate_agent_output
)
from .sql_guardrails import SQLGuardrails, GuardrailViolation


def get_db_config() -> dict:
    """
    Get database configuration from environment variables.
    Supports both local development and cloud databases (Vercel Postgres, Neon, etc.)
    """
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "retail_erp"),
        "user": os.getenv("DB_USER", os.getenv("USER", "postgres")),
        "password": os.getenv("DB_PASSWORD", ""),
        "sslmode": os.getenv("DB_SSLMODE"),  # "require" for cloud DBs
    }


def create_db_connection() -> "DatabaseConnection":
    """Create a database connection from environment variables."""
    config = get_db_config()
    return DatabaseConnection(
        host=config["host"],
        port=config["port"],
        database=config["database"],
        user=config["user"],
        password=config["password"],
        sslmode=config["sslmode"],
    )


class DatabaseConnection:
    """Database connection manager."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "retail_erp",
        user: str = "arushigupta",
        password: str = "",
        sslmode: str = None
    ):
        self.config = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password
        }
        # Add SSL mode for cloud databases (Vercel Postgres, Neon, etc.)
        if sslmode:
            self.config["sslmode"] = sslmode
        self._conn = None

    def connect(self):
        """Establish database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(**self.config)
        return self._conn

    def close(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()

    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute query and return results as list of dicts."""
        conn = self.connect()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            results = cur.fetchall()
            # Convert Decimal to float for JSON serialization
            return [self._convert_row(dict(row)) for row in results]

    def execute_scalar(self, query: str, params: tuple = None) -> Any:
        """Execute query and return single value."""
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone()
            if result:
                val = result[0]
                if isinstance(val, Decimal):
                    return float(val)
                return val
            return None

    def _convert_row(self, row: Dict) -> Dict:
        """Convert Decimal and date types for JSON serialization."""
        converted = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                converted[key] = float(value)
            elif isinstance(value, (date, datetime)):
                converted[key] = value.isoformat()
            else:
                converted[key] = value
        return converted

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class GuardrailedDatabaseConnection(DatabaseConnection):
    """
    Database connection with SQL guardrails enforcement.

    Validates all queries against role-based rules before execution.
    Provides defense-in-depth alongside database-level permissions.
    """

    def __init__(
        self,
        role: str,
        host: str = "localhost",
        port: int = 5432,
        database: str = "retail_erp",
        user: str = "arushigupta",
        password: str = "",
        sslmode: str = None,
        enforce_guardrails: bool = True
    ):
        super().__init__(host, port, database, user, password, sslmode)
        self.role = role.upper()
        self.enforce_guardrails = enforce_guardrails
        self._guardrails = SQLGuardrails(role) if enforce_guardrails else None
        self._violation_log: List[Dict] = []

    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute query with guardrail enforcement."""
        if self.enforce_guardrails and self._guardrails:
            # Validate query
            is_valid, error = self._guardrails.validate(query)
            if not is_valid:
                self._log_violation(query, error)
                raise GuardrailViolation(error)

            # Apply row limit
            query = self._guardrails.wrap_with_limit(query)

        # Set statement timeout for this query
        conn = self.connect()
        if self.enforce_guardrails and self._guardrails:
            timeout_ms = int(self._guardrails.get_timeout() * 1000)
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {timeout_ms}")

        return super().execute_query(query, params)

    def execute_scalar(self, query: str, params: tuple = None) -> Any:
        """Execute scalar query with guardrail enforcement."""
        if self.enforce_guardrails and self._guardrails:
            is_valid, error = self._guardrails.validate(query)
            if not is_valid:
                self._log_violation(query, error)
                raise GuardrailViolation(error)

        return super().execute_scalar(query, params)

    def _log_violation(self, query: str, error: str) -> None:
        """Log guardrail violation for audit."""
        self._violation_log.append({
            'role': self.role,
            'query': query[:500],
            'error': error,
        })

    def get_violation_log(self) -> List[Dict]:
        """Get the log of guardrail violations."""
        return self._violation_log.copy()

    def get_guardrails(self) -> Optional[SQLGuardrails]:
        """Get the guardrails instance."""
        return self._guardrails


class BaseAgent(ABC):
    """
    Abstract base class for all boardroom agents.

    Each agent must implement:
    - role: The agent's role (CEO, CFO, CMO, CIO)
    - analyze(): Perform analysis and return AgentOutput

    Security:
    - Uses GuardrailedDatabaseConnection for defense-in-depth
    - All queries are validated against role-based rules
    - Queries are limited by timeout and row count
    """

    # Set to True to enable guardrails (default for v2 agents)
    ENABLE_GUARDRAILS = True

    def __init__(self, db: DatabaseConnection = None, enforce_guardrails: bool = None):
        """
        Initialize agent with database connection.

        Args:
            db: Optional database connection (if None, creates guardrailed connection)
            enforce_guardrails: Override guardrail enforcement (default: class ENABLE_GUARDRAILS)
        """
        if enforce_guardrails is None:
            enforce_guardrails = self.ENABLE_GUARDRAILS

        if db is not None:
            self.db = db
        elif enforce_guardrails:
            # Create guardrailed connection using agent's role
            self.db = GuardrailedDatabaseConnection(
                role=self._get_role_name(),
                enforce_guardrails=True
            )
        else:
            self.db = DatabaseConnection()

        self._evidence: List[Evidence] = []

    def _get_role_name(self) -> str:
        """Get role name for guardrails. Override if role property not yet available."""
        # This is called before role property is fully initialized
        # Subclasses can override if needed
        return "EVAL"  # Safe default - most permissive

    @property
    @abstractmethod
    def role(self) -> AgentRole:
        """Return the agent's role."""
        pass

    @abstractmethod
    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """
        Perform analysis and return structured output.

        Args:
            date_from: Start date for analysis (YYYY-MM-DD)
            date_to: End date for analysis (YYYY-MM-DD)

        Returns:
            AgentOutput conforming to the interface contract
        """
        pass

    def _add_evidence(self, view: str, filters: str, query_id: str = None):
        """Track evidence for transparency."""
        self._evidence.append(Evidence(view=view, filters=filters, query_id=query_id))

    def _clear_evidence(self):
        """Clear evidence for new analysis run."""
        self._evidence = []

    def _calculate_trend(self, current: float, previous: float) -> Trend:
        """Calculate trend based on current vs previous values."""
        if previous == 0:
            return Trend.FLAT
        change_pct = ((current - previous) / abs(previous)) * 100
        if change_pct > 1:
            return Trend.UP
        elif change_pct < -1:
            return Trend.DOWN
        return Trend.FLAT

    def _format_currency(self, value: float) -> str:
        """Format value as currency string."""
        if value >= 1_000_000:
            return f"${value/1_000_000:.2f}M"
        elif value >= 1_000:
            return f"${value/1_000:.1f}K"
        return f"${value:.2f}"

    def _format_percentage(self, value: float) -> str:
        """Format value as percentage string."""
        return f"{value:.1f}%"

    def run(self, date_from: str = None, date_to: str = None) -> str:
        """
        Run analysis and return JSON output.

        Args:
            date_from: Start date for analysis
            date_to: End date for analysis

        Returns:
            JSON string conforming to agent interface contract
        """
        self._clear_evidence()
        output = self.analyze(date_from, date_to)

        # Validate output
        errors = validate_agent_output(output)
        if errors:
            raise ValueError(f"Agent output validation failed: {errors}")

        return output.to_json()

    def get_date_range(self) -> tuple:
        """Get the date range of available data."""
        query = """
        SELECT
            MIN(sale_date) as min_date,
            MAX(sale_date) as max_date
        FROM retail.v_sales_daily_store_category
        """
        result = self.db.execute_query(query)
        if result:
            return result[0]['min_date'], result[0]['max_date']
        return None, None
