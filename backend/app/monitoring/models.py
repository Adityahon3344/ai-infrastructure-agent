# Monitoring reuses app.servers.models.ServerMetricSample as its storage model
# (kept there to avoid a circular import between servers <-> monitoring).
from app.servers.models import ServerMetricSample  # noqa: F401
