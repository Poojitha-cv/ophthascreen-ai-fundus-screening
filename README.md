# Ophthalmic Screening Backend (fundus images)

FastAPI + SQLAlchemy backend around the existing `convnext_tiny_v1` fundus model (unmodified).
**Research prototype. Not a medical device, not clinically validated. See `docs/MODEL_CARD.md`.**

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # torch/timm pinned to the bundle's export versions
cp .env.example .env                       # set OPH_SECRET_KEY for anything beyond local dev
python -m scripts.install_model --bundle /path/to/bundle_convnext_tiny_v1.zip   # copies model/, verifies SHA-256
python -m scripts.create_doctor --email dr@clinic.org --name "Dr. Name"        # doctors are CLI-created only
uvicorn app.main:create_app --factory --port 8000       # API docs: http://localhost:8000/docs
pip install -r requirements-dev.txt && pytest           # 51 tests
```

## What it does
| Requirement | Where |
|---|---|
| Patient / doctor login (JWT, argon2id, lockout) | `modules/auth` |
| Left/right image upload (a *screening* = one visit) | `POST /patients/{id}/screenings`, `POST /screenings/{id}/images` |
| Quality check | `modules/imaging/quality.py` |
| ConvNeXt-Tiny prediction | `modules/inference/engine.py` wraps the bundle's `FundusScreener` |
| Patients, images, results, history | `modules/patients`, `screenings` (`GET /patients/{id}/screenings`) |
| Doctor dashboard | `GET /dashboard/summary`, `GET /dashboard/queue`, `POST /predictions/{id}/reviews` |
| Modular for clinical data later | `docs/EXTENDING.md` |

Typical doctor flow: `queue` (sorted: AI-flagged abnormal → model-uncertain → highest risk) → `GET /images/{id}`
(+ `/file?max_side=1024`) → `POST /predictions/{prediction_id}/reviews`.

## Design decisions you should know about
- **No fake data anywhere.** Nothing is seeded. Tests use synthetic images only to exercise plumbing.
- **Doctors cannot self-register** (a doctor can read every patient). Create them with `scripts/create_doctor.py`.
- **Patients do not see raw AI output by default** (`OPH_PATIENT_CAN_SEE_AI_RESULTS=false`): the model card says it is
  not for diagnosis. Patients see upload/quality status and whether a doctor has reviewed it.
- **Model integrity:** weights SHA-256 is checked against `export_manifest.json` at startup. Every prediction stores model
  tag, weights hash and the thresholds/temperature in effect, so old results stay interpretable after a model swap.
- **Both operating points are exposed** (screening threshold 0.108 and max-F1 0.475). Disease flags exist only for the 21
  "core" classes; other classes are returned as `validated: false` probabilities. `needs_review` is carried through as-is.
- **Upload is two-phase:** image + quality report are committed first, then the model runs. A model crash/outage leaves
  the image safe (`analysis_status` = `failed`/`pending`) and re-runnable via `POST /images/{id}/analyze`.
- **Retakes** supersede the previous image for that eye (kept as history). Re-analysis appends a new prediction and sends
  the image back to `pending_review`.
- Original uploaded bytes are stored untouched (not re-encoded). Every PHI read/write is in `audit_log`.

## Limitations (not done)
- **Quality check is an unvalidated heuristic** (blur, brightness, contrast, field coverage, colour). Only unusable images
  hard-fail. Calibrate with `python -m scripts.quality_stats --dir <real images>` and set `OPH_QUALITY__*`.
- The quality checks and model outputs were only exercised on synthetic images here; **no real fundus photo was run**.
  Model accuracy is as reported in the model card (RFMiD, 3 cameras, single centre); expect different results on other cameras.
- All doctors see all patients (no care-team assignment). No refresh tokens, no rate limiting beyond account lockout,
  no encryption of PHI at rest (use disk/DB encryption), no Alembic migrations yet (`create_all` at startup),
  no virus scanning. Inference runs in-process under a lock (fine for one worker; use a job queue for scale).
  A patient self-registering is not linked to a doctor-created record for the same person.
- Behind a proxy: set a body-size limit (e.g. nginx `client_max_body_size 60m`), TLS, and run uvicorn with `--proxy-headers`.
- Disease code → name mapping is **not shipped** (it must come from the dataset paper). Drop a `disease_names.json`
  (`{"DR": "..."}`) into `models/convnext_tiny_v1/` and the API will show names.
- Grad-CAM is not part of the exported model and is not implemented.
