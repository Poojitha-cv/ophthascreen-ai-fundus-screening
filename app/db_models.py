# """Imports every ORM model so Base.metadata knows all tables. A new module's models.py must be listed here."""
# from app.core.audit import AuditLog  # noqa: F401
# from app.modules.auth.models import User  # noqa: F401
# from app.modules.patients.models import Patient  # noqa: F401
# from app.modules.reviews.models import DoctorReview  # noqa: F401
# from app.modules.screenings.models import FundusImage, Prediction, Screening  # noqa: F401



# new version with clincally data
"""Imports every ORM model so Base.metadata knows all tables. A new module's models.py must be listed here."""
from app.core.audit import AuditLog  # noqa: F401
from app.modules.auth.models import User  # noqa: F401
from app.modules.patients.models import Patient  # noqa: F401
from app.modules.reviews.models import DoctorReview  # noqa: F401
from app.modules.risk.models import ClinicalRecord, ScreeningRisk  # noqa: F401
from app.modules.screenings.models import FundusImage, Prediction, Screening  # noqa: F401
