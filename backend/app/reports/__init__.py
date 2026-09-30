"""Automated incident reporting.

build_incident_report() assembles a markdown incident report purely from
database rows — no invented content. Empty sections say so explicitly.
"""

from app.reports.incident_report import build_incident_report

__all__ = ["build_incident_report"]
