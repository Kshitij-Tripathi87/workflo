
from app.models.asset import GraphSnapshot


def get_all_downstream(
    snapshot: GraphSnapshot, start_urn: str, visited: set[str] | None = None
) -> list[str]:
    if visited is None:
        visited = set()

    result: list[str] = []
    node = snapshot.nodes.get(start_urn)
    if not node:
        return result

    for downstream_urn in node.downstream:
        if downstream_urn not in visited and downstream_urn in snapshot.nodes:
            visited.add(downstream_urn)
            result.append(downstream_urn)
            result.extend(get_all_downstream(snapshot, downstream_urn, visited))

    return result
