# # from __future__ import annotations

# # import io

# # from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
# # from fastapi.responses import FileResponse
# # from PIL import Image
# # from sqlalchemy.orm import Session

# # from app.core.audit import audit
# # from app.core.config import Settings
# # from app.core.deps import get_current_user, get_db, get_engine, get_settings_dep, get_storage, require_doctor
# # from app.core.pagination import Page, PageParams
# # from app.modules.auth.models import User
# # from app.modules.patients.service import get_accessible_patient
# # from app.modules.screenings import service
# # from app.modules.screenings.models import Eye
# # from app.modules.screenings.schemas import ImageOut, ScreeningOut
# # from app.modules.screenings.serializers import image_out, screening_out

# # router = APIRouter(tags=["screenings"])


# # def _ctx(request: Request, db: Session, settings: Settings, storage, engine, user: User) -> service.Ctx:
# #     return service.Ctx(db=db, settings=settings, storage=storage, engine=engine, user=user, request=request)


# # def _names(engine) -> dict[str, str]:
# #     return engine.disease_names if engine is not None else {}


# # @router.post("/patients/{patient_id}/screenings", response_model=ScreeningOut, status_code=status.HTTP_201_CREATED)
# # def create_screening(patient_id: str, request: Request,
# #                      left_image: UploadFile | None = File(None, description="Left-eye fundus image (JPEG/PNG). Omit the field if not available."),
# #                      right_image: UploadFile | None = File(None, description="Right-eye fundus image (JPEG/PNG). Omit the field if not available."),
# #                      user: User = Depends(get_current_user), db: Session = Depends(get_db),
# #                      settings: Settings = Depends(get_settings_dep), storage=Depends(get_storage), engine=Depends(get_engine)):
# #     """Create a screening (visit) with a left and/or right fundus image. Each image is validated, quality-checked
# #     and, unless the quality check hard-fails, analysed by the model. Patients may only upload for themselves."""
# #     patient = get_accessible_patient(db, user, patient_id)
# #     s = service.create_screening(_ctx(request, db, settings, storage, engine, user), patient,
# #                                  {Eye.LEFT: left_image, Eye.RIGHT: right_image})
# #     return screening_out(s, user, settings, _names(engine))


# # @router.get("/patients/{patient_id}/screenings", response_model=Page[ScreeningOut])
# # def patient_history(patient_id: str, include_superseded: bool = False, pg: PageParams = Depends(),
# #                     user: User = Depends(get_current_user), db: Session = Depends(get_db),
# #                     settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
# #     """Screening history, newest first. Superseded (retaken) images are hidden unless include_superseded=true."""
# #     patient = get_accessible_patient(db, user, patient_id)
# #     rows, total = service.list_screenings(db, patient.id, pg.offset, pg.size)
# #     return Page(items=[screening_out(s, user, settings, _names(engine), include_superseded) for s in rows],
# #                 total=total, page=pg.page, size=pg.size)


# # @router.get("/screenings/{screening_id}", response_model=ScreeningOut)
# # def get_screening(screening_id: str, include_superseded: bool = False, user: User = Depends(get_current_user),
# #                   db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
# #     s = service.get_accessible_screening(db, user, screening_id)
# #     return screening_out(s, user, settings, _names(engine), include_superseded)


# # @router.post("/screenings/{screening_id}/images", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
# # def add_image(screening_id: str, request: Request, eye: Eye = Form(...), image: UploadFile = File(...),
# #               user: User = Depends(get_current_user), db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep),
# #               storage=Depends(get_storage), engine=Depends(get_engine)):
# #     """Add the missing eye, or upload a retake. A new image for an eye that already has one supersedes it (old one kept)."""
# #     s = service.get_accessible_screening(db, user, screening_id)
# #     img = service.add_image(_ctx(request, db, settings, storage, engine, user), s, eye, image)
# #     return image_out(img, user, settings, _names(engine))


# # @router.get("/images/{image_id}", response_model=ImageOut)
# # def get_image(image_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db),
# #               settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
# #     return image_out(service.get_accessible_image(db, user, image_id), user, settings, _names(engine))


# # @router.get("/images/{image_id}/file")
# # def get_image_file(image_id: str, request: Request, max_side: int | None = Query(None, ge=64, le=2048, description="Return a JPEG preview downscaled to this longest side"),
# #                    user: User = Depends(get_current_user), db: Session = Depends(get_db), storage=Depends(get_storage)):
# #     """The stored original (unmodified bytes), or a downscaled JPEG preview. Access is audited."""
# #     img = service.get_accessible_image(db, user, image_id)
# #     audit(db, request, user.id, "image.view", "image", img.id)
# #     db.commit()
# #     headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
# #     path = storage.path(img.storage_key)
# #     if max_side is None:
# #         return FileResponse(path, media_type=img.content_type, headers=headers)
# #     with Image.open(path) as im:
# #         im = im.convert("RGB")
# #         im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
# #         buf = io.BytesIO()
# #         im.save(buf, "JPEG", quality=88)
# #     return Response(buf.getvalue(), media_type="image/jpeg", headers=headers)


# # @router.post("/images/{image_id}/analyze", response_model=ImageOut)
# # def reanalyze_image(image_id: str, request: Request, doctor: User = Depends(require_doctor), db: Session = Depends(get_db),
# #                     settings: Settings = Depends(get_settings_dep), storage=Depends(get_storage), engine=Depends(get_engine)):
# #     """Re-run the model on a stored image (e.g. it was uploaded while the model was unavailable). Appends a new prediction."""
# #     img = service.get_accessible_image(db, doctor, image_id)
# #     img = service.reanalyze(_ctx(request, db, settings, storage, engine, doctor), img)
# #     return image_out(img, doctor, settings, _names(engine))


# from __future__ import annotations

# import base64
# import io

# from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
# from fastapi.responses import FileResponse
# from PIL import Image
# from sqlalchemy.orm import Session

# from app.core.audit import audit
# from app.core.config import Settings
# from app.core.deps import get_current_user, get_db, get_engine, get_settings_dep, get_storage, require_doctor
# from app.core.pagination import Page, PageParams
# from app.modules.auth.models import User
# from app.modules.patients.service import get_accessible_patient
# from app.modules.screenings import service
# from app.modules.screenings.models import Eye
# from app.modules.inference.protocol import GRADCAM_NOTICE, RISK_TARGET
# from app.modules.inference.rfmid_labels import RFMID_NAMES
# from app.modules.screenings.schemas import GradCamOut, ImageOut, ScreeningOut
# from app.modules.screenings.serializers import image_out, screening_out

# router = APIRouter(tags=["screenings"])


# def _ctx(request: Request, db: Session, settings: Settings, storage, engine, user: User) -> service.Ctx:
#     return service.Ctx(db=db, settings=settings, storage=storage, engine=engine, user=user, request=request)


# def _names(engine) -> dict[str, str]:
#     return engine.disease_names if engine is not None else {}


# @router.post("/patients/{patient_id}/screenings", response_model=ScreeningOut, status_code=status.HTTP_201_CREATED)
# def create_screening(patient_id: str, request: Request,
#                      left_image: UploadFile | None = File(None, description="Left-eye fundus image (JPEG/PNG). Omit the field if not available."),
#                      right_image: UploadFile | None = File(None, description="Right-eye fundus image (JPEG/PNG). Omit the field if not available."),
#                      user: User = Depends(get_current_user), db: Session = Depends(get_db),
#                      settings: Settings = Depends(get_settings_dep), storage=Depends(get_storage), engine=Depends(get_engine)):
#     """Create a screening (visit) with a left and/or right fundus image. Each image is validated, quality-checked
#     and, unless the quality check hard-fails, analysed by the model. Patients may only upload for themselves."""
#     patient = get_accessible_patient(db, user, patient_id)
#     s = service.create_screening(_ctx(request, db, settings, storage, engine, user), patient,
#                                  {Eye.LEFT: left_image, Eye.RIGHT: right_image})
#     return screening_out(s, user, settings, _names(engine))


# @router.get("/patients/{patient_id}/screenings", response_model=Page[ScreeningOut])
# def patient_history(patient_id: str, include_superseded: bool = False, pg: PageParams = Depends(),
#                     user: User = Depends(get_current_user), db: Session = Depends(get_db),
#                     settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
#     """Screening history, newest first. Superseded (retaken) images are hidden unless include_superseded=true."""
#     patient = get_accessible_patient(db, user, patient_id)
#     rows, total = service.list_screenings(db, patient.id, pg.offset, pg.size)
#     return Page(items=[screening_out(s, user, settings, _names(engine), include_superseded) for s in rows],
#                 total=total, page=pg.page, size=pg.size)


# @router.get("/screenings/{screening_id}", response_model=ScreeningOut)
# def get_screening(screening_id: str, include_superseded: bool = False, user: User = Depends(get_current_user),
#                   db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
#     s = service.get_accessible_screening(db, user, screening_id)
#     return screening_out(s, user, settings, _names(engine), include_superseded)


# @router.post("/screenings/{screening_id}/images", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
# def add_image(screening_id: str, request: Request, eye: Eye = Form(...), image: UploadFile = File(...),
#               user: User = Depends(get_current_user), db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep),
#               storage=Depends(get_storage), engine=Depends(get_engine)):
#     """Add the missing eye, or upload a retake. A new image for an eye that already has one supersedes it (old one kept)."""
#     s = service.get_accessible_screening(db, user, screening_id)
#     img = service.add_image(_ctx(request, db, settings, storage, engine, user), s, eye, image)
#     return image_out(img, user, settings, _names(engine))


# @router.get("/images/{image_id}", response_model=ImageOut)
# def get_image(image_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db),
#               settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
#     return image_out(service.get_accessible_image(db, user, image_id), user, settings, _names(engine))


# @router.get("/images/{image_id}/file")
# def get_image_file(image_id: str, request: Request, max_side: int | None = Query(None, ge=64, le=2048, description="Return a JPEG preview downscaled to this longest side"),
#                    user: User = Depends(get_current_user), db: Session = Depends(get_db), storage=Depends(get_storage)):
#     """The stored original (unmodified bytes), or a downscaled JPEG preview. Access is audited."""
#     img = service.get_accessible_image(db, user, image_id)
#     audit(db, request, user.id, "image.view", "image", img.id)
#     db.commit()
#     headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
#     path = storage.path(img.storage_key)
#     if max_side is None:
#         return FileResponse(path, media_type=img.content_type, headers=headers)
#     with Image.open(path) as im:
#         im = im.convert("RGB")
#         im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
#         buf = io.BytesIO()
#         im.save(buf, "JPEG", quality=88)
#     return Response(buf.getvalue(), media_type="image/jpeg", headers=headers)


# @router.post("/images/{image_id}/analyze", response_model=ImageOut)
# def reanalyze_image(image_id: str, request: Request, doctor: User = Depends(require_doctor), db: Session = Depends(get_db),
#                     settings: Settings = Depends(get_settings_dep), storage=Depends(get_storage), engine=Depends(get_engine)):
#     """Re-run the model on a stored image (e.g. it was uploaded while the model was unavailable). Appends a new prediction."""
#     img = service.get_accessible_image(db, doctor, image_id)
#     img = service.reanalyze(_ctx(request, db, settings, storage, engine, doctor), img)
#     return image_out(img, doctor, settings, _names(engine))


# @router.get("/images/{image_id}/gradcam", response_model=GradCamOut)
# def image_gradcam(image_id: str, request: Request, target: str = Query(RISK_TARGET, description="'risk' (Disease_Risk) or a validated RFMiD class code, e.g. DR"),
#                   doctor: User = Depends(require_doctor), db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep),
#                   storage=Depends(get_storage), engine=Depends(get_engine)):
#     """Grad-CAM attention map for the image's latest prediction. Doctors only. Computed on demand (cached in memory), never stored.
#     The map is drawn on the model's input view (fundus cropped and squared), so it will not line up pixel-for-pixel with the raw upload."""
#     img = service.get_accessible_image(db, doctor, image_id)
#     pred, res = service.gradcam(_ctx(request, db, settings, storage, engine, doctor), img, target)
#     names = {**RFMID_NAMES, **_names(engine)}
#     return GradCamOut(image_id=img.id, prediction_id=pred.id, target=res.target,
#                       target_name="Abnormal-risk score (Disease_Risk)" if res.target == RISK_TARGET else names.get(res.target, res.target),
#                       empty=res.empty, overlay_jpeg_base64=base64.b64encode(res.overlay_jpeg).decode("ascii"),
#                       resolution=res.resolution, grid_size=res.grid_size, model_tag=pred.model_tag,
#                       model_weights_sha256=pred.model_weights_sha256, notice=GRADCAM_NOTICE)



from __future__ import annotations

import base64
import io

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import Settings
from app.core.deps import get_current_user, get_db, get_engine, get_settings_dep, get_storage, require_doctor
from app.core.pagination import Page, PageParams
from app.modules.auth.models import User
from app.modules.patients.service import get_accessible_patient
from app.modules.risk import service as risk_service
from app.modules.screenings import service
from app.modules.screenings.models import Eye
from app.modules.inference.protocol import GRADCAM_NOTICE, RISK_TARGET
from app.modules.inference.rfmid_labels import RFMID_NAMES
from app.modules.screenings.schemas import GradCamOut, ImageOut, ScreeningOut
from app.modules.screenings.serializers import image_out, screening_out

router = APIRouter(tags=["screenings"])


def _ctx(request: Request, db: Session, settings: Settings, storage, engine, user: User) -> service.Ctx:
    return service.Ctx(db=db, settings=settings, storage=storage, engine=engine, user=user, request=request)


def _names(engine) -> dict[str, str]:
    return engine.disease_names if engine is not None else {}


@router.post("/patients/{patient_id}/screenings", response_model=ScreeningOut, status_code=status.HTTP_201_CREATED)
def create_screening(patient_id: str, request: Request,
                     left_image: UploadFile | None = File(None, description="Left-eye fundus image (JPEG/PNG). Omit the field if not available."),
                     right_image: UploadFile | None = File(None, description="Right-eye fundus image (JPEG/PNG). Omit the field if not available."),
                     clinical: str | None = Form(None, description="Optional clinical record as a JSON object (see POST /screenings/{id}/clinical for the fields). "
                                                                   "Patients may send symptoms/history only; VA, IOP and CDR are doctor-only."),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings_dep), storage=Depends(get_storage), engine=Depends(get_engine)):
    """Create a screening (visit) with a left and/or right fundus image. Each image is validated, quality-checked
    and, unless the quality check hard-fails, analysed by the model. Patients may only upload for themselves."""
    patient = get_accessible_patient(db, user, patient_id)
    clinical_in = risk_service.parse_clinical_json(clinical, user)     # validated (and role-checked) before anything is written
    s = service.create_screening(_ctx(request, db, settings, storage, engine, user), patient,
                                 {Eye.LEFT: left_image, Eye.RIGHT: right_image}, clinical=clinical_in)
    return screening_out(s, user, settings, _names(engine), extras=risk_service.extras_for(db, [s.id]))


@router.get("/patients/{patient_id}/screenings", response_model=Page[ScreeningOut])
def patient_history(patient_id: str, include_superseded: bool = False, pg: PageParams = Depends(),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
    """Screening history, newest first. Superseded (retaken) images are hidden unless include_superseded=true."""
    patient = get_accessible_patient(db, user, patient_id)
    rows, total = service.list_screenings(db, patient.id, pg.offset, pg.size)
    extras = risk_service.extras_for(db, [s.id for s in rows])
    return Page(items=[screening_out(s, user, settings, _names(engine), include_superseded, extras) for s in rows],
                total=total, page=pg.page, size=pg.size)


@router.get("/screenings/{screening_id}", response_model=ScreeningOut)
def get_screening(screening_id: str, include_superseded: bool = False, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
    s = service.get_accessible_screening(db, user, screening_id)
    return screening_out(s, user, settings, _names(engine), include_superseded, risk_service.extras_for(db, [s.id]))


@router.post("/screenings/{screening_id}/images", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
def add_image(screening_id: str, request: Request, eye: Eye = Form(...), image: UploadFile = File(...),
              user: User = Depends(get_current_user), db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep),
              storage=Depends(get_storage), engine=Depends(get_engine)):
    """Add the missing eye, or upload a retake. A new image for an eye that already has one supersedes it (old one kept)."""
    s = service.get_accessible_screening(db, user, screening_id)
    img = service.add_image(_ctx(request, db, settings, storage, engine, user), s, eye, image)
    return image_out(img, user, settings, _names(engine))


@router.get("/images/{image_id}", response_model=ImageOut)
def get_image(image_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db),
              settings: Settings = Depends(get_settings_dep), engine=Depends(get_engine)):
    return image_out(service.get_accessible_image(db, user, image_id), user, settings, _names(engine))


@router.get("/images/{image_id}/file")
def get_image_file(image_id: str, request: Request, max_side: int | None = Query(None, ge=64, le=2048, description="Return a JPEG preview downscaled to this longest side"),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db), storage=Depends(get_storage)):
    """The stored original (unmodified bytes), or a downscaled JPEG preview. Access is audited."""
    img = service.get_accessible_image(db, user, image_id)
    audit(db, request, user.id, "image.view", "image", img.id)
    db.commit()
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    path = storage.path(img.storage_key)
    if max_side is None:
        return FileResponse(path, media_type=img.content_type, headers=headers)
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
    return Response(buf.getvalue(), media_type="image/jpeg", headers=headers)


@router.post("/images/{image_id}/analyze", response_model=ImageOut)
def reanalyze_image(image_id: str, request: Request, doctor: User = Depends(require_doctor), db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings_dep), storage=Depends(get_storage), engine=Depends(get_engine)):
    """Re-run the model on a stored image (e.g. it was uploaded while the model was unavailable). Appends a new prediction."""
    img = service.get_accessible_image(db, doctor, image_id)
    img = service.reanalyze(_ctx(request, db, settings, storage, engine, doctor), img)
    return image_out(img, doctor, settings, _names(engine))


@router.get("/images/{image_id}/gradcam", response_model=GradCamOut)
def image_gradcam(image_id: str, request: Request, target: str = Query(RISK_TARGET, description="'risk' (Disease_Risk) or a validated RFMiD class code, e.g. DR"),
                  doctor: User = Depends(require_doctor), db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep),
                  storage=Depends(get_storage), engine=Depends(get_engine)):
    """Grad-CAM attention map for the image's latest prediction. Doctors only. Computed on demand (cached in memory), never stored.
    The map is drawn on the model's input view (fundus cropped and squared), so it will not line up pixel-for-pixel with the raw upload."""
    img = service.get_accessible_image(db, doctor, image_id)
    pred, res = service.gradcam(_ctx(request, db, settings, storage, engine, doctor), img, target)
    names = {**RFMID_NAMES, **_names(engine)}
    return GradCamOut(image_id=img.id, prediction_id=pred.id, target=res.target,
                      target_name="Abnormal-risk score (Disease_Risk)" if res.target == RISK_TARGET else names.get(res.target, res.target),
                      empty=res.empty, overlay_jpeg_base64=base64.b64encode(res.overlay_jpeg).decode("ascii"),
                      resolution=res.resolution, grid_size=res.grid_size, model_tag=pred.model_tag,
                      model_weights_sha256=pred.model_weights_sha256, notice=GRADCAM_NOTICE)
