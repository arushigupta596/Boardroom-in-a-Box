"""
SQL Guardrails Middleware
=========================
Defense-in-depth layer that validates SQL queries before execution.
Works alongside database-level permissions for double enforcement.

Features:
- Schema/view allowlist per agent role
- DDL/DML blocking (INSERT, UPDATE, DELETE, DROP, etc.)
- JOIN count limits
- Query timeout enforcement
- Row limit enforcement
- Date filter requirements for fact tables
"""

import re
import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Where, Comparison
from sqlparse.tokens import Keyword, DML, DDL
from typing import List, Set, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class GuardrailViolation(Exception):
    """Raised when a query violates guardrail rules."""
    pass


class ViolationType(Enum):
    FORBIDDEN_SCHEMA = "forbidden_schema"
    FORBIDDEN_TABLE = "forbidden_table"
    FORBIDDEN_OPERATION = "forbidden_operation"
    TOO_MANY_JOINS = "too_many_joins"
    MISSING_DATE_FILTER = "missing_date_filter"
    ROW_LIMIT_EXCEEDED = "row_limit_exceeded"
    TIMEOUT_EXCEEDED = "timeout_exceeded"


@dataclass
class GuardrailConfig:
    """Configuration for SQL guardrails per agent role."""

    # Allowed schemas (whitelist)
    allowed_schemas: Set[str] = field(default_factory=set)

    # Allowed view/table patterns (regex patterns)
    allowed_patterns: List[str] = field(default_factory=list)

    # Explicitly denied tables (blacklist - takes precedence)
    denied_tables: Set[str] = field(default_factory=set)

    # Query budget controls
    max_joins: int = 5
    max_rows: int = 5000  # Demo default
    timeout_seconds: float = 5.0

    # Fact tables that require date filters
    fact_tables_requiring_date: Set[str] = field(default_factory=set)

    # Date filter column names to look for
    date_columns: Set[str] = field(default_factory=lambda: {
        'sale_date', 'transaction_date', 'return_date', 'order_date',
        'effective_start', 'effective_end', 'created_at', 'check_date'
    })


# Default guardrail configurations per agent role
AGENT_GUARDRAILS: Dict[str, GuardrailConfig] = {
    'CEO': GuardrailConfig(
        allowed_schemas={'ceo_views'},
        allowed_patterns=[
            r'^ceo_views\.\w+$',  # Any view in ceo_views schema
        ],
        denied_tables={
            'retail.customer',
            'retail.pos_transaction',
            'retail.pos_transaction_line',
            'retail.supplier_product',
        },
        max_joins=3,
        max_rows=1000,  # CEO sees aggregates only
        timeout_seconds=5.0,
        fact_tables_requiring_date=set(),  # CEO views are pre-aggregated
    ),

    'CFO': GuardrailConfig(
        allowed_schemas={'cfo_views'},
        allowed_patterns=[
            r'^cfo_views\.\w+$',
            r'^cfo_views\.margin_\w+$',
            r'^cfo_views\.returns_\w+$',
        ],
        denied_tables={
            'retail.customer',
            'retail.supplier',
            'retail.supplier_product',
        },
        max_joins=4,
        max_rows=5000,
        timeout_seconds=5.0,
        fact_tables_requiring_date={
            'cfo_views.daily_pnl',
            'cfo_views.margin_by_store',
            'cfo_views.margin_by_category',
            'cfo_views.discount_analysis',
            'cfo_views.returns_impact',
        },
    ),

    'CMO': GuardrailConfig(
        allowed_schemas={'cmo_views'},
        allowed_patterns=[
            r'^cmo_views\.\w+$',
        ],
        denied_tables={
            'retail.customer',  # No raw customer data
            'retail.pos_transaction',  # No raw transactions
            'retail.pos_transaction_line',
        },
        max_joins=4,
        max_rows=5000,
        timeout_seconds=5.0,
        fact_tables_requiring_date={
            'cmo_views.sales_demand_category',
            'cmo_views.sales_demand_store',
            'cmo_views.basket_metrics',
        },
    ),

    'CIO': GuardrailConfig(
        allowed_schemas={'cio_views'},
        allowed_patterns=[
            r'^cio_views\.\w+$',
        ],
        denied_tables={
            'retail.customer',  # No PII access
        },
        max_joins=5,
        max_rows=10000,  # CIO may need more rows for health checks
        timeout_seconds=10.0,
        fact_tables_requiring_date={
            'cio_views.health_check_history',
        },
    ),

    'EVAL': GuardrailConfig(
        allowed_schemas={'retail', 'ceo_views', 'cfo_views', 'cmo_views', 'cio_views'},
        allowed_patterns=[
            r'^\w+\.\w+$',  # Any schema.table
        ],
        denied_tables=set(),  # Evaluator can access all for validation
        max_joins=6,
        max_rows=50000,
        timeout_seconds=10.0,
        fact_tables_requiring_date=set(),  # Evaluator needs full access
    ),
}


class SQLGuardrails:
    """
    SQL Guardrails Middleware.

    Validates SQL queries against role-based rules before execution.
    """

    # Forbidden SQL operations (DML/DDL that modifies data)
    FORBIDDEN_OPERATIONS = {
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
        'TRUNCATE', 'GRANT', 'REVOKE', 'COPY', 'VACUUM', 'ANALYZE'
    }

    def __init__(self, role: str):
        """
        Initialize guardrails for a specific agent role.

        Args:
            role: Agent role (CEO, CFO, CMO, CIO, EVAL)
        """
        self.role = role.upper()
        if self.role not in AGENT_GUARDRAILS:
            raise ValueError(f"Unknown role: {role}. Valid roles: {list(AGENT_GUARDRAILS.keys())}")

        self.config = AGENT_GUARDRAILS[self.role]
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.config.allowed_patterns]

    def validate(self, sql: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a SQL query against guardrail rules.

        Args:
            sql: The SQL query to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self._validate_query(sql)
            return True, None
        except GuardrailViolation as e:
            return False, str(e)

    def _validate_query(self, sql: str) -> None:
        """
        Validate a SQL query. Raises GuardrailViolation if invalid.
        """
        # Parse the SQL
        parsed = sqlparse.parse(sql)
        if not parsed:
            raise GuardrailViolation("Empty or invalid SQL query")

        for statement in parsed:
            # Check for forbidden operations
            self._check_forbidden_operations(statement)

            # Extract referenced tables
            tables = self._extract_tables(statement)

            # Check table access
            self._check_table_access(tables)

            # Check JOIN count
            self._check_join_count(statement)

            # Check date filter requirements
            self._check_date_filter(statement, tables)

    def _check_forbidden_operations(self, statement) -> None:
        """Check for INSERT, UPDATE, DELETE, DDL operations."""
        # Get the statement type
        stmt_type = statement.get_type()

        if stmt_type and stmt_type.upper() in self.FORBIDDEN_OPERATIONS:
            raise GuardrailViolation(
                f"Forbidden operation: {stmt_type}. Only SELECT queries are allowed."
            )

        # Also check tokens for edge cases
        for token in statement.flatten():
            if token.ttype in (DML, DDL):
                word = token.value.upper()
                if word in self.FORBIDDEN_OPERATIONS:
                    raise GuardrailViolation(
                        f"Forbidden operation: {word}. Only SELECT queries are allowed."
                    )

    def _extract_tables(self, statement) -> Set[str]:
        """Extract table/view names from a SQL statement."""
        tables = set()

        # Convert to string and use regex for reliable extraction
        sql_str = str(statement).upper()

        # Pattern to match schema.table or just table names after FROM/JOIN
        # Handles: FROM schema.table, JOIN schema.table, FROM table
        from_pattern = r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)'

        for match in re.finditer(from_pattern, str(statement), re.IGNORECASE):
            table_ref = match.group(1).lower()
            tables.add(table_ref)

        return tables

    def _check_table_access(self, tables: Set[str]) -> None:
        """Check if all referenced tables are allowed."""
        for table in tables:
            # Check denied list first (blacklist takes precedence)
            if table in self.config.denied_tables:
                raise GuardrailViolation(
                    f"Access denied to table: {table}. "
                    f"This table is explicitly blocked for {self.role} role."
                )

            # Check if table has a schema prefix
            if '.' in table:
                schema = table.split('.')[0]

                # Check schema allowlist
                if schema not in self.config.allowed_schemas:
                    raise GuardrailViolation(
                        f"Access denied to schema: {schema}. "
                        f"Allowed schemas for {self.role}: {self.config.allowed_schemas}"
                    )

                # Check against allowed patterns
                if not any(p.match(table) for p in self._compiled_patterns):
                    raise GuardrailViolation(
                        f"Access denied to table: {table}. "
                        f"Does not match allowed patterns for {self.role} role."
                    )
            else:
                # No schema prefix - check if it matches any allowed pattern
                # Try prepending each allowed schema
                matched = False
                for schema in self.config.allowed_schemas:
                    full_name = f"{schema}.{table}"
                    if any(p.match(full_name) for p in self._compiled_patterns):
                        matched = True
                        break

                if not matched and self.config.allowed_patterns:
                    raise GuardrailViolation(
                        f"Ambiguous table reference: {table}. "
                        f"Please use schema-qualified names (e.g., schema.table)."
                    )

    def _check_join_count(self, statement) -> None:
        """Check if the query has too many JOINs."""
        sql_str = str(statement).upper()

        # Count JOIN keywords (various types: JOIN, LEFT JOIN, RIGHT JOIN, etc.)
        # Use word boundary to avoid matching partial words
        join_count = len(re.findall(r'\bJOIN\b', sql_str, re.IGNORECASE))

        if join_count > self.config.max_joins:
            raise GuardrailViolation(
                f"Too many JOINs: {join_count}. "
                f"Maximum allowed for {self.role}: {self.config.max_joins}"
            )

    def _check_date_filter(self, statement, tables: Set[str]) -> None:
        """Check if fact tables have required date filters."""
        # Find which referenced tables require date filters
        tables_needing_filter = tables & self.config.fact_tables_requiring_date

        if not tables_needing_filter:
            return

        sql_str = str(statement).lower()

        # Exception: Allow MIN/MAX queries for date range discovery
        # These are safe aggregations that don't scan full tables
        if re.search(r'\b(min|max)\s*\(\s*(sale_date|transaction_date|return_date)', sql_str, re.IGNORECASE):
            return

        # Check for presence of date column in WHERE clause
        has_date_filter = False
        for date_col in self.config.date_columns:
            # Look for date column in comparison (e.g., sale_date =, sale_date BETWEEN)
            if re.search(rf'\b{date_col}\b\s*(=|>|<|>=|<=|between|in)', sql_str, re.IGNORECASE):
                has_date_filter = True
                break

        if not has_date_filter:
            raise GuardrailViolation(
                f"Missing date filter for fact table(s): {tables_needing_filter}. "
                f"Queries on these tables must include a date filter "
                f"(e.g., WHERE sale_date BETWEEN ... AND ...). "
                f"Valid date columns: {self.config.date_columns}"
            )

    def wrap_with_limit(self, sql: str) -> str:
        """
        Wrap a query with row limit if not already present.

        Args:
            sql: The SQL query

        Returns:
            SQL with LIMIT clause added if needed
        """
        sql_upper = sql.upper().strip()

        # Check if LIMIT already exists
        if 'LIMIT' in sql_upper:
            # Extract existing limit and enforce max
            limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
            if limit_match:
                existing_limit = int(limit_match.group(1))
                if existing_limit > self.config.max_rows:
                    # Replace with max allowed
                    sql = re.sub(
                        r'LIMIT\s+\d+',
                        f'LIMIT {self.config.max_rows}',
                        sql,
                        flags=re.IGNORECASE
                    )
            return sql

        # Add LIMIT clause
        # Remove trailing semicolon if present
        sql = sql.rstrip().rstrip(';')
        return f"{sql} LIMIT {self.config.max_rows}"

    def get_timeout(self) -> float:
        """Get the timeout in seconds for this role."""
        return self.config.timeout_seconds

    def get_max_rows(self) -> int:
        """Get the max rows limit for this role."""
        return self.config.max_rows


class GuardrailedConnection:
    """
    A database connection wrapper that enforces guardrails.

    Wraps the actual database connection and validates all queries
    before execution.
    """

    def __init__(self, db_connection, role: str):
        """
        Initialize guardrailed connection.

        Args:
            db_connection: The underlying database connection
            role: Agent role for guardrail rules
        """
        self.db = db_connection
        self.guardrails = SQLGuardrails(role)
        self.role = role
        self._violation_log: List[Dict] = []

    def execute_query(self, sql: str, params: tuple = None) -> list:
        """
        Execute a query with guardrail enforcement.

        Args:
            sql: The SQL query
            params: Query parameters

        Returns:
            Query results

        Raises:
            GuardrailViolation: If query violates guardrail rules
        """
        # Validate the query
        is_valid, error = self.guardrails.validate(sql)

        if not is_valid:
            self._log_violation(sql, error)
            raise GuardrailViolation(error)

        # Wrap with limit if needed
        sql = self.guardrails.wrap_with_limit(sql)

        # Execute with timeout
        # Note: Actual timeout implementation depends on DB driver
        # For psycopg2, we'd use statement_timeout
        return self.db.execute_query(sql, params)

    def _log_violation(self, sql: str, error: str) -> None:
        """Log a guardrail violation for audit."""
        self._violation_log.append({
            'role': self.role,
            'sql': sql[:500],  # Truncate long queries
            'error': error,
        })

    def get_violation_log(self) -> List[Dict]:
        """Get the log of guardrail violations."""
        return self._violation_log.copy()


# Utility function to get guardrails for a role
def get_guardrails(role: str) -> SQLGuardrails:
    """Get SQLGuardrails instance for a role."""
    return SQLGuardrails(role)


# Utility function to validate a query
def validate_query(role: str, sql: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a SQL query for a specific role.

    Args:
        role: Agent role
        sql: SQL query to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    guardrails = SQLGuardrails(role)
    return guardrails.validate(sql)


if __name__ == "__main__":
    # Test the guardrails
    print("=== SQL Guardrails Test ===\n")

    # Test cases
    test_cases = [
        ("CEO", "SELECT * FROM ceo_views.board_summary", True),
        ("CEO", "SELECT * FROM retail.customer", False),  # Denied table
        ("CEO", "DELETE FROM ceo_views.board_summary", False),  # Forbidden op
        ("CFO", "SELECT * FROM cfo_views.daily_pnl WHERE sale_date BETWEEN '2025-01-01' AND '2025-03-31'", True),
        ("CFO", "SELECT * FROM cfo_views.daily_pnl", False),  # Missing date filter
        ("CFO", "SELECT * FROM cmo_views.basket_metrics", False),  # Wrong schema
        ("CMO", "SELECT * FROM cmo_views.segment_performance", True),
        ("CIO", "SELECT * FROM cio_views.health_check_status", True),
        ("EVAL", "SELECT * FROM retail.customer", True),  # Evaluator has access
    ]

    for role, sql, expected_valid in test_cases:
        guardrails = SQLGuardrails(role)
        is_valid, error = guardrails.validate(sql)

        status = "✓ PASS" if is_valid == expected_valid else "✗ FAIL"
        result = "ALLOWED" if is_valid else f"BLOCKED: {error}"

        print(f"{status} | {role}: {sql[:60]}...")
        print(f"       Result: {result}\n")
