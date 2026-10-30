# Import every model so Alembic can see them through Base.metadata.
from app.models.appointment import Appointment, AppointmentStatus  # noqa: F401
from app.models.availability import Availability  # noqa: F401
from app.models.doctor import Doctor  # noqa: F401
from app.models.user import Role, User  # noqa: F401
