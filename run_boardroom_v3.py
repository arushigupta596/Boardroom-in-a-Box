#!/usr/bin/env python3
"""
Boardroom-in-a-Box v3 Runner
============================
Full orchestrated flow with handoffs, evaluation, and artifacts.

Usage:
    python run_boardroom_v3.py                    # KPI Review (default)
    python run_boardroom_v3.py --flow trade-off  # Trade-off debate
    python run_boardroom_v3.py --flow scenario   # Scenario simulation
    python run_boardroom_v3.py --mode audit      # Audit mode
    python run_boardroom_v3.py --export memo     # Export board memo
"""

import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, '.')

from agents.flow_orchestrator import (
    FlowOrchestrator, FlowType, BoardMode, FLOW_SPECS,
    run_kpi_review, run_trade_off, run_scenario
)
from agents.confidence_engine import assess_confidence
from agents.export_artifacts import (
    export_memo, export_evidence, export_decision_log, export_email
)


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def print_section(text: str):
    """Print a section header."""
    print(f"\n--- {text} ---")


def run_flow(flow_type: str, mode: str, date_from: str, date_to: str):
    """Run the specified flow."""
    flow_map = {
        'kpi-review': FlowType.KPI_REVIEW,
        'trade-off': FlowType.TRADE_OFF,
        'scenario': FlowType.SCENARIO,
        'root-cause': FlowType.ROOT_CAUSE,
        'board-memo': FlowType.BOARD_MEMO,
    }
    mode_map = {
        'summary': BoardMode.SUMMARY,
        'debate': BoardMode.DEBATE,
        'operator': BoardMode.OPERATOR,
        'audit': BoardMode.AUDIT,
    }

    ft = flow_map.get(flow_type, FlowType.KPI_REVIEW)
    bm = mode_map.get(mode, BoardMode.SUMMARY)

    orchestrator = FlowOrchestrator()
    session = orchestrator.start_session(
        ft,
        mode=bm,
        period_start=date_from,
        period_end=date_to,
    )
    return orchestrator.run_flow(session)


def display_session(session, verbose: bool = False):
    """Display session results."""

    print_header(f"BOARDROOM SESSION: {session.session_id}")
    print(f"Flow: {session.flow_spec.name}")
    print(f"Mode: {session.mode.value}")
    print(f"Period: {session.period_start} to {session.period_end}")

    # Data Confidence
    print_section("DATA CONFIDENCE")
    if session.confidence:
        conf = session.confidence
        icon = "✓" if conf.can_proceed else "✗"
        print(f"  {icon} Level: {conf.level.value}")
        print(f"    Score: {conf.score:.1f}/100")
        print(f"    Can Proceed: {conf.can_proceed}")
        if conf.blocking_issues:
            print("    Blocking Issues:")
            for issue in conf.blocking_issues:
                print(f"      - {issue}")

    # Constraints Status
    print_section("DECISION CONSTRAINTS")
    for key, status in session.constraints_status.items():
        constraint = session.constraints.get(key, {})
        icon = "✓" if status == "PASS" else "✗"
        name = constraint.get("name", key)
        value = constraint.get("value", "N/A")
        unit = constraint.get("unit", "")
        print(f"  {icon} {name}: {value}{unit} ({status})")

    # Flow Timeline
    print_section("FLOW TIMELINE")
    for name, node in session.nodes.items():
        icon = "✓" if node.status == "completed" else "✗" if node.status == "failed" else "○"
        print(f"  {icon} {name}: {node.status}")

    # Handoffs
    print_section("HANDOFFS")
    for handoff in session.handoffs:
        print(f"  {handoff.handoff_from} → {handoff.handoff_to}")
        if handoff.reason:
            print(f"    Reason: {handoff.reason}")
        if handoff.flags:
            print(f"    Flags: {', '.join(handoff.flags)}")

    # Evaluation
    if session.evaluation:
        eval_out = session.evaluation
        print_section("EVALUATOR RESULTS")
        print(f"  Overall Score: {eval_out.overall_score:.1f}/10")
        print(f"  Risk Level: {eval_out.risk_level}")
        print(f"  Confidence: {eval_out.confidence}")

        if eval_out.conflicts:
            print("\n  Conflicts:")
            for conflict in eval_out.conflicts:
                print(f"    [{conflict.severity.value}] {conflict.issue}")
                print(f"      Between: {', '.join(conflict.between)}")
                if conflict.resolution:
                    print(f"      Resolution: {conflict.resolution}")

        if eval_out.decisions:
            print("\n  Decisions:")
            for i, decision in enumerate(eval_out.decisions, 1):
                print(f"    {i}. {decision.action}")
                print(f"       Impact: {decision.impact}")
                print(f"       Priority: {decision.priority}")

        if verbose:
            print("\n  Dimension Scores:")
            for dim in eval_out.dimension_scores:
                print(f"    {dim.dimension}: {dim.score:.1f} × {dim.weight:.0%} = {dim.weighted_score:.2f}")

    # Agent Outputs (summary)
    print_section("AGENT SUMMARIES")
    for agent_name in ["CEO", "CFO", "CMO", "CIO"]:
        output = session.agent_outputs.get(agent_name)
        if output:
            print(f"\n  {agent_name}:")
            for insight in output.insights[:2]:
                print(f"    - {insight}")


def main():
    parser = argparse.ArgumentParser(
        description="Run Boardroom-in-a-Box v3 (orchestrated flows)"
    )
    parser.add_argument(
        '--flow',
        choices=['kpi-review', 'trade-off', 'scenario', 'root-cause', 'board-memo'],
        default='kpi-review',
        help='Flow type to run'
    )
    parser.add_argument(
        '--mode',
        choices=['summary', 'debate', 'operator', 'audit'],
        default='summary',
        help='Display mode'
    )
    parser.add_argument(
        '--date-from',
        default='2025-01-01',
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--date-to',
        default='2025-03-31',
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--export',
        choices=['memo', 'evidence', 'log', 'email', 'json'],
        help='Export artifact type'
    )
    parser.add_argument(
        '--output',
        help='Output file path'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--confidence-only',
        action='store_true',
        help='Only check data confidence'
    )

    args = parser.parse_args()

    # Confidence-only mode
    if args.confidence_only:
        print_header("DATA CONFIDENCE CHECK")
        report = assess_confidence()
        print(f"Level: {report.level.value}")
        print(f"Score: {report.score:.1f}/100")
        print(f"Can Proceed: {report.can_proceed}")
        print(f"\nSummary: {report.summary}")
        if report.blocking_issues:
            print("\nBlocking Issues:")
            for issue in report.blocking_issues:
                print(f"  - {issue}")
        if report.warnings:
            print("\nWarnings:")
            for warn in report.warnings:
                print(f"  - {warn}")
        return

    # Run flow
    session = run_flow(args.flow, args.mode, args.date_from, args.date_to)

    # Export if requested
    if args.export:
        if args.export == 'memo':
            output = export_memo(session)
        elif args.export == 'evidence':
            output = json.dumps(export_evidence(session), indent=2)
        elif args.export == 'log':
            output = json.dumps(export_decision_log(session), indent=2)
        elif args.export == 'email':
            output = export_email(session)
        elif args.export == 'json':
            output = session.to_json()

        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"Exported to {args.output}")
        else:
            print(output)
        return

    # Display results
    display_session(session, verbose=args.verbose)

    print_header("SESSION COMPLETE")
    print(f"Session ID: {session.session_id}")
    print(f"Started: {session.started_at}")
    print(f"Ended: {session.ended_at}")
    print("\nExport options:")
    print(f"  python run_boardroom_v3.py --export memo --output memo.md")
    print(f"  python run_boardroom_v3.py --export evidence --output evidence.json")


if __name__ == "__main__":
    main()
