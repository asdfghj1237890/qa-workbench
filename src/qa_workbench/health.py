"""Pure health-observation contract shared by host adapters and samplers.

Constructing evidence performs no probes, reads, clock access or status inference.
The adapter supplies measurements and their provenance explicitly.
"""

from copy import deepcopy


def observation(module, status="unknown", reason="not_connected", *, observed=None,
                freshness="unmeasured", value=None, unit="none", threshold=None,
                metric="not_measured", source="not_connected", last_success=None,
                details=None):
    """Build detached public evidence without promoting unknown data to healthy."""
    return {
        "id": module, "status": status, "reason": reason, "freshness": freshness,
        "observed_at": observed.isoformat() if observed else None,
        "last_success_at": last_success.isoformat() if last_success else None,
        "source": source,
        "measurement": {"key": metric, "value": value, "unit": unit,
                        "threshold": threshold},
        "details": deepcopy(details) if details is not None else {},
    }
