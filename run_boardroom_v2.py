#!/usr/bin/env python3
"""
Boardroom-in-a-Box Runner v2
============================
Runs scope-enforced agents that use ONLY their allowed views.
Each agent is restricted to their designated data surface.
"""

import sys
import json
import argparse
from datetime import datetime

# Add agents directory to path
sys.path.insert(0, '.')

from agents.contract import AgentOutput, AgentRole
from agents.base_agent import DatabaseConnection

# Import v2 (scope-enforced) agents
from agents.ceo_agent_v2 import CEOAgentV2
from agents.cfo_agent_v2 import CFOAgentV2
from agents.cmo_agent_v2 import CMOAgentV2
from agents.cio_agent_v2 import CIOAgentV2
from agents.evaluator_agent import EvaluatorAgent


def get_agent_data_surface(db: DatabaseConnection) -> dict:
    """Get the allowed data surface for each agent."""
    query = """
    SELECT agent_role, schema_name || '.' || view_name AS view_name, access_level
    FROM retail.agent_data_surface
    ORDER BY agent_role, view_name
    """
    results = db.execute_query(query)

    surface = {}
    for r in results:
        role = r['agent_role']
        if role not in surface:
            surface[role] = {'allowed': [], 'denied': []}

        if r['access_level'] == 'ALLOWED':
            surface[role]['allowed'].append(r['view_name'])
        else:
            surface[role]['denied'].append(r['view_name'])

    return surface


def run_single_agent(role: str, date_from: str = None, date_to: str = None) -> str:
    """Run a single scope-enforced agent and return JSON output."""
    agents = {
        'ceo': CEOAgentV2,
        'cfo': CFOAgentV2,
        'cmo': CMOAgentV2,
        'cio': CIOAgentV2
    }

    if role.lower() not in agents:
        raise ValueError(f"Unknown agent role: {role}. Valid: {list(agents.keys())}")

    agent = agents[role.lower()]()
    return agent.run(date_from, date_to)


def run_all_agents(date_from: str = None, date_to: str = None) -> tuple:
    """Run all scope-enforced agents and return combined output."""
    agents = [CEOAgentV2(), CFOAgentV2(), CMOAgentV2(), CIOAgentV2()]
    outputs = {}
    agent_outputs = []

    for agent in agents:
        output = agent.analyze(date_from, date_to)
        outputs[agent.role.value] = output.to_dict()
        agent_outputs.append(output)

    return outputs, agent_outputs


def run_boardroom_with_evaluation(date_from: str = None, date_to: str = None) -> dict:
    """Run all scope-enforced agents and evaluate the results."""
    # Get data surface registry
    db = DatabaseConnection()
    data_surface = get_agent_data_surface(db)

    # Run all agents
    outputs_dict, agent_outputs = run_all_agents(date_from, date_to)

    # Evaluate
    evaluator = EvaluatorAgent()
    evaluation = evaluator.evaluate_boardroom(agent_outputs)

    return {
        "version": "2.0",
        "description": "Scope-enforced agents using role-based view schemas",
        "timestamp": datetime.now().isoformat(),
        "date_range": {
            "from": date_from,
            "to": date_to
        },
        "data_surface": data_surface,
        "agents": outputs_dict,
        "evaluation": evaluation.to_dict()
    }


def print_data_surface():
    """Print the data surface registry."""
    db = DatabaseConnection()
    surface = get_agent_data_surface(db)

    print("\n" + "=" * 70)
    print("AGENT DATA SURFACE REGISTRY")
    print("=" * 70)

    for role in ['CEO', 'CFO', 'CMO', 'CIO']:
        if role in surface:
            print(f"\n{role} AGENT:")
            print("  ALLOWED:")
            for view in surface[role]['allowed']:
                print(f"    ✓ {view}")
            if surface[role]['denied']:
                print("  DENIED:")
                for view in surface[role]['denied']:
                    print(f"    ✗ {view}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Run Boardroom-in-a-Box v2 (scope-enforced agents)"
    )
    parser.add_argument(
        '--agent',
        choices=['ceo', 'cfo', 'cmo', 'cio', 'all'],
        default='all',
        help='Which agent to run (default: all)'
    )
    parser.add_argument(
        '--date-from',
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--date-to',
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--evaluate',
        action='store_true',
        help='Include evaluation scoring'
    )
    parser.add_argument(
        '--pretty',
        action='store_true',
        help='Pretty print JSON output'
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: stdout)'
    )
    parser.add_argument(
        '--show-surface',
        action='store_true',
        help='Show data surface registry and exit'
    )

    args = parser.parse_args()

    # Show data surface if requested
    if args.show_surface:
        print_data_surface()
        return

    # Run agents
    if args.agent == 'all':
        if args.evaluate:
            result = run_boardroom_with_evaluation(args.date_from, args.date_to)
        else:
            outputs_dict, _ = run_all_agents(args.date_from, args.date_to)
            result = {
                "version": "2.0",
                "timestamp": datetime.now().isoformat(),
                "date_range": {
                    "from": args.date_from,
                    "to": args.date_to
                },
                "agents": outputs_dict
            }
    else:
        result = json.loads(run_single_agent(args.agent, args.date_from, args.date_to))

    # Format output
    indent = 2 if args.pretty else None
    output_json = json.dumps(result, indent=indent)

    # Write output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output_json)
        print(f"Output written to {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
