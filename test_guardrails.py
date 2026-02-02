#!/usr/bin/env python3
"""
Test SQL Guardrails Integration
===============================
Tests that guardrails are properly enforced at the tool layer.
"""

import sys
sys.path.insert(0, '.')

from agents.sql_guardrails import SQLGuardrails, GuardrailViolation, validate_query
from agents.base_agent import GuardrailedDatabaseConnection, DatabaseConnection


def test_guardrails_unit():
    """Unit tests for SQL guardrails."""
    print("=" * 70)
    print("UNIT TESTS: SQL Guardrails")
    print("=" * 70)

    tests = [
        # (role, sql, should_pass, description)

        # CEO Tests
        ("CEO", "SELECT * FROM ceo_views.board_summary", True,
         "CEO can access ceo_views"),
        ("CEO", "SELECT * FROM retail.customer", False,
         "CEO blocked from retail.customer (denied table)"),
        ("CEO", "SELECT * FROM cfo_views.daily_pnl WHERE sale_date = '2025-01-01'", False,
         "CEO blocked from cfo_views (wrong schema)"),
        ("CEO", "DELETE FROM ceo_views.board_summary WHERE 1=1", False,
         "CEO blocked from DELETE operation"),
        ("CEO", "INSERT INTO ceo_views.board_summary VALUES (1)", False,
         "CEO blocked from INSERT operation"),
        ("CEO", "DROP TABLE ceo_views.board_summary", False,
         "CEO blocked from DROP operation"),

        # CFO Tests
        ("CFO", "SELECT * FROM cfo_views.daily_pnl WHERE sale_date BETWEEN '2025-01-01' AND '2025-03-31'", True,
         "CFO can access cfo_views with date filter"),
        ("CFO", "SELECT * FROM cfo_views.daily_pnl", False,
         "CFO blocked without date filter on fact table"),
        ("CFO", "SELECT * FROM cfo_views.inventory_value", True,
         "CFO can access non-fact views without date filter"),
        ("CFO", "SELECT * FROM retail.customer", False,
         "CFO blocked from retail.customer"),
        ("CFO", "SELECT * FROM cmo_views.basket_metrics WHERE sale_date = '2025-01-01'", False,
         "CFO blocked from cmo_views (wrong schema)"),

        # CMO Tests
        ("CMO", "SELECT * FROM cmo_views.segment_performance", True,
         "CMO can access cmo_views"),
        ("CMO", "SELECT * FROM cmo_views.basket_metrics WHERE sale_date = '2025-01-01'", True,
         "CMO can access basket_metrics with date filter"),
        ("CMO", "SELECT * FROM cmo_views.basket_metrics", False,
         "CMO blocked without date filter on fact table"),
        ("CMO", "SELECT * FROM retail.customer", False,
         "CMO blocked from retail.customer"),

        # CIO Tests
        ("CIO", "SELECT * FROM cio_views.health_check_status", True,
         "CIO can access cio_views"),
        ("CIO", "SELECT * FROM cio_views.data_freshness", True,
         "CIO can access data_freshness"),
        ("CIO", "SELECT * FROM retail.customer", False,
         "CIO blocked from retail.customer (PII)"),

        # EVAL Tests (most permissive)
        ("EVAL", "SELECT * FROM retail.customer", True,
         "Evaluator can access retail.customer"),
        ("EVAL", "SELECT * FROM ceo_views.board_summary", True,
         "Evaluator can access ceo_views"),
        ("EVAL", "SELECT * FROM cfo_views.daily_pnl", True,
         "Evaluator can access cfo_views (no date filter required)"),
        ("EVAL", "DELETE FROM retail.customer WHERE 1=1", False,
         "Evaluator still blocked from DELETE"),

        # JOIN count tests
        ("CEO", """
            SELECT * FROM ceo_views.board_summary a
            JOIN ceo_views.margin_summary b ON 1=1
            JOIN ceo_views.revenue_summary c ON 1=1
            JOIN ceo_views.category_performance d ON 1=1
            JOIN ceo_views.regional_performance e ON 1=1
        """, False, "CEO blocked with too many JOINs (4 > max 3)"),

        ("CFO", """
            SELECT * FROM cfo_views.daily_pnl a
            JOIN cfo_views.margin_by_store b ON 1=1
            JOIN cfo_views.margin_by_category c ON 1=1
            JOIN cfo_views.inventory_value d ON 1=1
            WHERE a.sale_date = '2025-01-01'
        """, True, "CFO allowed with 3 JOINs (within limit of 4)"),
    ]

    passed = 0
    failed = 0

    for role, sql, should_pass, description in tests:
        is_valid, error = validate_query(role, sql)

        if is_valid == should_pass:
            status = "✓ PASS"
            passed += 1
        else:
            status = "✗ FAIL"
            failed += 1

        result = "ALLOWED" if is_valid else f"BLOCKED"
        print(f"{status} | {description}")
        print(f"       {role}: {result}")
        if error:
            print(f"       Reason: {error[:80]}...")
        print()

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_guardrails_integration():
    """Integration tests with actual database connection."""
    print("\n" + "=" * 70)
    print("INTEGRATION TESTS: Guardrailed Database Connection")
    print("=" * 70)

    tests_passed = 0
    tests_failed = 0

    # Test 1: CEO can query allowed view
    print("\nTest 1: CEO querying allowed view...")
    try:
        db = GuardrailedDatabaseConnection(role="CEO")
        result = db.execute_query("SELECT * FROM ceo_views.board_summary")
        print(f"  ✓ PASS: Got {len(result)} row(s)")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1

    # Test 2: CEO blocked from forbidden table
    print("\nTest 2: CEO blocked from retail.customer...")
    try:
        db = GuardrailedDatabaseConnection(role="CEO")
        result = db.execute_query("SELECT * FROM retail.customer")
        print(f"  ✗ FAIL: Query should have been blocked")
        tests_failed += 1
    except GuardrailViolation as e:
        print(f"  ✓ PASS: Correctly blocked - {str(e)[:60]}...")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: Wrong exception type: {e}")
        tests_failed += 1

    # Test 3: CFO blocked without date filter
    print("\nTest 3: CFO blocked without date filter on fact table...")
    try:
        db = GuardrailedDatabaseConnection(role="CFO")
        result = db.execute_query("SELECT * FROM cfo_views.daily_pnl")
        print(f"  ✗ FAIL: Query should have been blocked (no date filter)")
        tests_failed += 1
    except GuardrailViolation as e:
        print(f"  ✓ PASS: Correctly blocked - {str(e)[:60]}...")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: Wrong exception type: {e}")
        tests_failed += 1

    # Test 4: CFO allowed with date filter
    print("\nTest 4: CFO allowed with date filter...")
    try:
        db = GuardrailedDatabaseConnection(role="CFO")
        result = db.execute_query(
            "SELECT * FROM cfo_views.daily_pnl WHERE sale_date BETWEEN '2025-01-01' AND '2025-03-31'"
        )
        print(f"  ✓ PASS: Got {len(result)} row(s)")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1

    # Test 5: Row limit enforcement
    print("\nTest 5: Row limit enforcement (CEO max 1000)...")
    try:
        db = GuardrailedDatabaseConnection(role="CEO")
        # This view has few rows, but we verify LIMIT is added
        guardrails = db.get_guardrails()
        sql = "SELECT * FROM ceo_views.board_summary"
        wrapped = guardrails.wrap_with_limit(sql)
        if "LIMIT 1000" in wrapped:
            print(f"  ✓ PASS: LIMIT 1000 added to query")
            tests_passed += 1
        else:
            print(f"  ✗ FAIL: LIMIT not added. Got: {wrapped}")
            tests_failed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1

    # Test 6: DELETE operation blocked
    print("\nTest 6: DELETE operation blocked...")
    try:
        db = GuardrailedDatabaseConnection(role="EVAL")
        result = db.execute_query("DELETE FROM retail.brand WHERE 1=0")
        print(f"  ✗ FAIL: DELETE should have been blocked")
        tests_failed += 1
    except GuardrailViolation as e:
        print(f"  ✓ PASS: Correctly blocked - {str(e)[:60]}...")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: Wrong exception type: {e}")
        tests_failed += 1

    # Test 7: Violation logging
    print("\nTest 7: Violation logging...")
    try:
        db = GuardrailedDatabaseConnection(role="CEO")
        try:
            db.execute_query("SELECT * FROM retail.customer")
        except GuardrailViolation:
            pass

        violations = db.get_violation_log()
        if len(violations) > 0 and violations[0]['role'] == 'CEO':
            print(f"  ✓ PASS: Violation logged correctly")
            tests_passed += 1
        else:
            print(f"  ✗ FAIL: Violation not logged")
            tests_failed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1

    print(f"\nIntegration Results: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


def test_agent_with_guardrails():
    """Test that agents use guardrails correctly."""
    print("\n" + "=" * 70)
    print("AGENT TESTS: V2 Agents with Guardrails")
    print("=" * 70)

    from agents.ceo_agent_v2 import CEOAgentV2
    from agents.cfo_agent_v2 import CFOAgentV2
    from agents.cmo_agent_v2 import CMOAgentV2
    from agents.cio_agent_v2 import CIOAgentV2

    tests_passed = 0
    tests_failed = 0

    # Test each agent runs successfully with guardrails
    agents = [
        ("CEO", CEOAgentV2),
        ("CFO", CFOAgentV2),
        ("CMO", CMOAgentV2),
        ("CIO", CIOAgentV2),
    ]

    for name, AgentClass in agents:
        print(f"\nTest: {name} Agent with guardrails...")
        try:
            agent = AgentClass()
            output = agent.analyze()
            print(f"  ✓ PASS: {name} agent ran successfully")
            print(f"       KPIs: {len(output.kpis)}, Insights: {len(output.insights)}")
            tests_passed += 1
        except GuardrailViolation as e:
            print(f"  ✗ FAIL: {name} agent hit guardrail: {e}")
            tests_failed += 1
        except Exception as e:
            print(f"  ✗ FAIL: {name} agent error: {e}")
            tests_failed += 1

    print(f"\nAgent Results: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


def main():
    print("\n" + "=" * 70)
    print("SQL GUARDRAILS TEST SUITE")
    print("=" * 70)

    all_passed = True

    # Run unit tests
    if not test_guardrails_unit():
        all_passed = False

    # Run integration tests
    if not test_guardrails_integration():
        all_passed = False

    # Run agent tests
    if not test_agent_with_guardrails():
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED ✓")
    else:
        print("SOME TESTS FAILED ✗")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
