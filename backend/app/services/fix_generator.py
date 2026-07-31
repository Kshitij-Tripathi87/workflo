from app.models import Incident, FixDraft

def generate_fix(incident: Incident) -> FixDraft:
    if incident.incident_type == "schema_drift":
        body = f"""-- Suggested remediation for {incident.asset_urn}
-- Review downstream dependencies before applying.
-- Align downstream logic to the current source schema.
"""
        return FixDraft(
            incident_id=incident.incident_id,
            title="Schema drift remediation draft",
            summary=incident.reason,
            artifact_type="sql",
            artifact_body=body,
            confidence=0.78,
        )

    body = """# Ownership gap remediation
- Assign a responsible owner
- Add stewardship metadata
- Re-run validation
"""
    return FixDraft(
        incident_id=incident.incident_id,
        title="Ownership remediation draft",
        summary=incident.reason,
        artifact_type="markdown",
        artifact_body=body,
        confidence=0.64,
    )
