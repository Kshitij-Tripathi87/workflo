from app.models import Incident
from app.connectors.datahub.client import DataHubClient

client = DataHubClient()


def analyze_blast_radius(incident: Incident, downstream_assets: list[str]) -> Incident:
    """Legacy function - sets blast_radius from downstream assets."""
    incident.blast_radius = downstream_assets[:10]
    
    # Update severity based on blast radius size
    if len(incident.blast_radius) >= 5:
        incident.severity = "critical"
    elif len(incident.blast_radius) >= 3:
        incident.severity = "high"
    
    return incident