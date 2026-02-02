"""
Export Artifacts - Executive-Ready Outputs
==========================================
Generates board memos, evidence packs, and shareable artifacts.

Exports:
- Board Memo (Markdown/HTML/PDF-ready)
- Evidence Pack (JSON)
- Decision Log (JSON)
- Summary for Email/Slack
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

from .flow_orchestrator import SessionState, BoardMode
from .evaluator_v2 import EvaluatorOutput
from .contract import AgentOutput


@dataclass
class ExportConfig:
    """Configuration for exports."""
    include_evidence: bool = True
    include_sql: bool = False  # Only for audit mode
    include_raw_data: bool = False
    max_insights_per_agent: int = 3
    max_recommendations: int = 5


class ArtifactExporter:
    """
    Generates executive-ready artifacts from session state.
    """

    def __init__(self, config: ExportConfig = None):
        self.config = config or ExportConfig()

    def generate_board_memo(self, session: SessionState) -> str:
        """
        Generate a board memo in Markdown format.

        Args:
            session: Completed session state

        Returns:
            Markdown string ready for rendering
        """
        lines = []

        # Header
        lines.append(f"# Board Summary")
        lines.append(f"**Session:** {session.session_id}")
        lines.append(f"**Flow:** {session.flow_spec.name}")
        lines.append(f"**Period:** {session.period_start or 'N/A'} to {session.period_end or 'N/A'}")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        # Data Confidence
        if session.confidence:
            conf = session.confidence
            icon = "✅" if conf.can_proceed else "⚠️"
            lines.append(f"## Data Confidence: {icon} {conf.level.value}")
            lines.append(f"> {conf.summary}")
            lines.append("")

        # Evaluator Summary
        if session.evaluation:
            eval_out = session.evaluation
            lines.append(f"## Executive Summary")
            lines.append("")
            lines.append(f"| Metric | Value |")
            lines.append(f"|--------|-------|")
            lines.append(f"| Overall Score | **{eval_out.overall_score:.1f}** / 10 |")
            lines.append(f"| Risk Level | {eval_out.risk_level} |")
            lines.append(f"| Confidence | {eval_out.confidence} |")
            lines.append(f"| Conflicts | {len(eval_out.conflicts)} |")
            lines.append("")

        # Constraints Status
        if session.constraints_status:
            lines.append("## Decision Constraints")
            lines.append("")
            for key, status in session.constraints_status.items():
                icon = "✅" if status == "PASS" else "❌"
                constraint = session.constraints.get(key, {})
                name = constraint.get("name", key)
                value = constraint.get("value", "N/A")
                unit = constraint.get("unit", "")
                lines.append(f"- {icon} **{name}:** {value}{unit} ({status})")
            lines.append("")

        # Key Metrics (from CEO output)
        ceo_output = session.agent_outputs.get("CEO")
        if ceo_output:
            lines.append("## Key Performance Indicators")
            lines.append("")
            lines.append("| KPI | Value | Trend | Window |")
            lines.append("|-----|-------|-------|--------|")
            for kpi in ceo_output.kpis[:4]:
                trend_icon = "↑" if kpi.trend.value == "UP" else "↓" if kpi.trend.value == "DOWN" else "→"
                lines.append(f"| {kpi.name} | {kpi.value} {kpi.unit} | {trend_icon} | {kpi.window} |")
            lines.append("")

        # Conflicts
        if session.evaluation and session.evaluation.conflicts:
            lines.append("## Conflicts Detected")
            lines.append("")
            for conflict in session.evaluation.conflicts:
                severity_icon = "🔴" if conflict.severity.value == "Critical" else "🟠" if conflict.severity.value == "High" else "🟡"
                lines.append(f"### {severity_icon} {conflict.issue}")
                lines.append(f"- **Between:** {', '.join(conflict.between)}")
                lines.append(f"- **Severity:** {conflict.severity.value}")
                if conflict.details:
                    lines.append(f"- **Details:** {conflict.details}")
                if conflict.resolution:
                    lines.append(f"- **Resolution:** {conflict.resolution}")
                lines.append("")

        # Agent Insights
        lines.append("## Agent Insights")
        lines.append("")

        for agent_name in ["CEO", "CFO", "CMO", "CIO"]:
            output = session.agent_outputs.get(agent_name)
            if output:
                lines.append(f"### {agent_name}")
                lines.append("")

                # Top insights
                for insight in output.insights[:self.config.max_insights_per_agent]:
                    lines.append(f"- {insight}")
                lines.append("")

                # Top risk if any
                if output.risks:
                    lines.append(f"**Key Risk:** {output.risks[0]}")
                    lines.append("")

        # Recommendations
        if session.evaluation:
            lines.append("## Recommended Actions")
            lines.append("")
            for i, decision in enumerate(session.evaluation.decisions[:self.config.max_recommendations], 1):
                lines.append(f"### {i}. {decision.action}")
                lines.append(f"- **Impact:** {decision.impact}")
                lines.append(f"- **Priority:** {decision.priority}")
                lines.append(f"- **Confidence:** {decision.confidence}")
                lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*Generated by Boardroom-in-a-Box | Mode: {session.mode.value}*")

        return "\n".join(lines)

    def generate_evidence_pack(self, session: SessionState) -> dict:
        """
        Generate evidence pack as JSON.

        Args:
            session: Completed session state

        Returns:
            Dictionary with all evidence
        """
        evidence = {
            "session_id": session.session_id,
            "generated_at": datetime.now().isoformat(),
            "period": {
                "start": session.period_start,
                "end": session.period_end,
            },
            "agents": {},
            "handoffs": [],
            "evaluation": None,
            "confidence": None,
        }

        # Agent evidence
        for agent_name, output in session.agent_outputs.items():
            evidence["agents"][agent_name] = {
                "kpis": [k.to_dict() for k in output.kpis],
                "insights": output.insights,
                "risks": output.risks,
                "recommendations": [r.to_dict() for r in output.recommendations],
                "evidence": [e.to_dict() for e in output.evidence],
                "confidence": output.confidence.value,
            }

        # Handoffs
        for handoff in session.handoffs:
            evidence["handoffs"].append(handoff.to_dict())

        # Evaluation
        if session.evaluation:
            evidence["evaluation"] = session.evaluation.to_dict()

        # Confidence
        if session.confidence:
            evidence["confidence"] = session.confidence.to_dict()

        return evidence

    def generate_decision_log(self, session: SessionState) -> dict:
        """
        Generate decision audit log.

        Args:
            session: Completed session state

        Returns:
            Dictionary with full audit trail
        """
        log = {
            "session_id": session.session_id,
            "flow": session.flow_spec.to_dict(),
            "mode": session.mode.value,
            "timing": {
                "started_at": session.started_at,
                "ended_at": session.ended_at,
            },
            "period": {
                "start": session.period_start,
                "end": session.period_end,
            },
            "constraints_applied": session.constraints,
            "constraints_status": session.constraints_status,
            "flow_execution": [],
            "evaluation_result": None,
            "data_confidence": None,
        }

        # Flow execution trace
        for agent_name, node in session.nodes.items():
            log["flow_execution"].append({
                "agent": agent_name,
                "status": node.status,
                "started_at": node.started_at,
                "ended_at": node.ended_at,
                "handoff": node.handoff_out.to_dict() if node.handoff_out else None,
            })

        # Edge connections
        log["edges"] = [e.to_dict() for e in session.edges]

        # Evaluation
        if session.evaluation:
            log["evaluation_result"] = {
                "overall_score": session.evaluation.overall_score,
                "risk_level": session.evaluation.risk_level,
                "confidence": session.evaluation.confidence,
                "conflicts_count": len(session.evaluation.conflicts),
                "constraints_violated": session.evaluation.constraints_violated,
                "decisions_count": len(session.evaluation.decisions),
            }

        # Confidence
        if session.confidence:
            log["data_confidence"] = {
                "level": session.confidence.level.value,
                "score": session.confidence.score,
                "can_proceed": session.confidence.can_proceed,
                "blocking_issues": session.confidence.blocking_issues,
            }

        return log

    def generate_email_summary(self, session: SessionState) -> str:
        """
        Generate a short summary suitable for email/Slack.

        Args:
            session: Completed session state

        Returns:
            Plain text summary
        """
        lines = []

        lines.append(f"📊 BOARDROOM SUMMARY | {session.flow_spec.name}")
        lines.append(f"Period: {session.period_start} to {session.period_end}")
        lines.append("")

        if session.evaluation:
            eval_out = session.evaluation
            lines.append(f"Score: {eval_out.overall_score:.1f}/10 | Risk: {eval_out.risk_level}")
            lines.append("")

        # Top KPIs
        ceo_output = session.agent_outputs.get("CEO")
        if ceo_output:
            lines.append("KEY METRICS:")
            for kpi in ceo_output.kpis[:3]:
                trend = "↑" if kpi.trend.value == "UP" else "↓" if kpi.trend.value == "DOWN" else "→"
                lines.append(f"• {kpi.name}: {kpi.value}{kpi.unit} {trend}")
            lines.append("")

        # Conflicts
        if session.evaluation and session.evaluation.conflicts:
            high_conflicts = [c for c in session.evaluation.conflicts
                            if c.severity.value in ["High", "Critical"]]
            if high_conflicts:
                lines.append(f"⚠️ {len(high_conflicts)} HIGH-PRIORITY CONFLICTS")
                for c in high_conflicts[:2]:
                    lines.append(f"• {c.issue}")
                lines.append("")

        # Top action
        if session.evaluation and session.evaluation.decisions:
            top = session.evaluation.decisions[0]
            lines.append(f"TOP ACTION: {top.action}")
            lines.append(f"Impact: {top.impact}")

        lines.append("")
        lines.append(f"View full report: [Session {session.session_id}]")

        return "\n".join(lines)

    def generate_slack_blocks(self, session: SessionState) -> List[Dict]:
        """
        Generate Slack Block Kit format.

        Args:
            session: Completed session state

        Returns:
            List of Slack blocks
        """
        blocks = []

        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 {session.flow_spec.name} Summary"
            }
        })

        # Context
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Period:* {session.period_start} to {session.period_end} | *Session:* {session.session_id}"
                }
            ]
        })

        blocks.append({"type": "divider"})

        # Score section
        if session.evaluation:
            eval_out = session.evaluation
            risk_emoji = "🟢" if eval_out.risk_level == "Low" else "🟡" if eval_out.risk_level == "Medium" else "🔴"

            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Overall Score*\n{eval_out.overall_score:.1f} / 10"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Risk Level*\n{risk_emoji} {eval_out.risk_level}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Confidence*\n{eval_out.confidence}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Conflicts*\n{len(eval_out.conflicts)}"
                    }
                ]
            })

        # Top metrics
        ceo_output = session.agent_outputs.get("CEO")
        if ceo_output:
            metrics_text = ""
            for kpi in ceo_output.kpis[:3]:
                trend = "↑" if kpi.trend.value == "UP" else "↓" if kpi.trend.value == "DOWN" else "→"
                metrics_text += f"• {kpi.name}: *{kpi.value}{kpi.unit}* {trend}\n"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Key Metrics:*\n{metrics_text}"
                }
            })

        # Top action button
        if session.evaluation and session.evaluation.decisions:
            top = session.evaluation.decisions[0]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommended Action:*\n{top.action}\n_Impact: {top.impact}_"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Details"
                    },
                    "action_id": f"view_session_{session.session_id}"
                }
            })

        return blocks


# Convenience functions
def export_memo(session: SessionState) -> str:
    """Export board memo."""
    exporter = ArtifactExporter()
    return exporter.generate_board_memo(session)


def export_evidence(session: SessionState) -> dict:
    """Export evidence pack."""
    exporter = ArtifactExporter()
    return exporter.generate_evidence_pack(session)


def export_decision_log(session: SessionState) -> dict:
    """Export decision log."""
    exporter = ArtifactExporter()
    return exporter.generate_decision_log(session)


def export_email(session: SessionState) -> str:
    """Export email summary."""
    exporter = ArtifactExporter()
    return exporter.generate_email_summary(session)
