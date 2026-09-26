"""Digital-twin sparring simulator for the autonomous defense loop.

The twin continuously attacks a virtual device with simulated ATT&CK
technique footprints and measures whether the REAL detection scoring path
(rules-v1 + ml-anomaly-v1, the same pure functions engine.scan_tenant uses)
catches them. Everything here is labeled simulated: twin events are never
written to the events table and never become real alerts.

Evasions (attacks the engine misses) are stashed as labeled training rows
so the retrain pipeline can learn from them — the self-learning loop.

Wiring (done by the parent, not here):
    from app.sparring.api import router as sparring_router
    app.include_router(sparring_router, prefix="/api/v1/sparring", tags=["sparring"])
and schedule app.sparring.loop.sparring_loop() in the lifespan.
"""

from app.sparring.models import SparringFinding, SparringRun
from app.sparring.runner import get_evasion_training_rows, run_sparring

__all__ = [
    "SparringFinding",
    "SparringRun",
    "get_evasion_training_rows",
    "run_sparring",
]
