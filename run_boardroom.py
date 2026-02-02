#!/usr/bin/env python3
"""
Boardroom-in-a-Box Runner
=========================
Runs all boardroom agents and produces evaluated output.
"""

import sys
import json
import argparse
from datetime import datetime

# Add agents directory to path
sys.path.insert(0, '.')

from agents.contract import AgentOutput, AgentRole
from agents.base_agent import DatabaseConnection
from agents.ceo_agent import CEOAgent
from agents.cfo_agent import CFOAgent
from agents.cmo_agent import CMOAgent
from agents.cio_agent import CIOAgent
from agents.evaluator_agent import EvaluatorAgent


def run_single_agent(role: str, date_from: str = None, date_to: str = None) -> str:
    """Run a single agent and return JSON output."""
    agents = {
        'ceo': CEOAgent,
        'cfo': CFOAgent,
        'cmo': CMOAgent,
        'cio': CIOAgent
    }

    if role.lower() not in agents:
        raise ValueError(f"Unknown agent role: {role}. Valid: {list(agents.keys())}")

    agent = agents[role.lower()]()
    return agent.run(date_from, date_to)


def run_all_agents(date_from: str = None, date_to: str = None) -> dict:
    """Run all agents and return combined output."""
    agents = [CEOAgent(), CFOAgent(), CMOAgent(), CIOAgent()]
    outputs = {}
    agent_outputs = []

    for agent in agents:
        output = agent.analyze(date_from, date_to)
        outputs[agent.role.value] = output.to_dict()
        agent_outputs.append(output)

    return outputs, agent_outputs


def run_boardroom_with_evaluation(date_from: str = None, date_to: str = None) -> dict:
    """Run all agents and evaluate the results."""
    # Run all agents
    outputs_dict, agent_outputs = run_all_agents(date_from, date_to)

    # Evaluate
    evaluator = EvaluatorAgent()
    evaluation = evaluator.evaluate_boardroom(agent_outputs)

    return {
        "timestamp": datetime.now().isoformat(),
        "date_range": {
            "from": date_from,
            "to": date_to
        },
        "agents": outputs_dict,
        "evaluation": evaluation.to_dict()
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run Boardroom-in-a-Box agents for retail analytics"
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

    args = parser.parse_args()

    # Run agents
    if args.agent == 'all':
        if args.evaluate:
            result = run_boardroom_with_evaluation(args.date_from, args.date_to)
        else:
            outputs_dict, _ = run_all_agents(args.date_from, args.date_to)
            result = {
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
