# Import all models here so SQLAlchemy's mapper registry is fully populated
# before any query runs. This prevents "failed to locate a name 'Team'" errors
# when the APScheduler correlation job triggers mapper initialization.
from app.models.team import Team  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.integration import Integration  # noqa: F401
from app.models.chat import ChatMessage  # noqa: F401
