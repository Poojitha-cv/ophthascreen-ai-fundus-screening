# Adding clinical data (and later, fusion)

The anchor is `Screening` (one patient visit). Images already hang off it; clinical data should too.

## 1. Add a module (no existing file changes except two registrations)
```
app/modules/clinical/{models,schemas,service,router}.py
```
```python
# models.py
class ClinicalRecord(Base):
    __tablename__ = "clinical_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    screening_id: Mapped[str] = mapped_column(ForeignKey("screenings.id"), unique=True)   # one per visit
    recorded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    # ...fields defined by your clinical team (versioned schema recommended)
```
Register it: add the import to `app/db_models.py` and the router to `API_ROUTERS` in `app/main.py`.
Reuse `get_accessible_patient` / `require_doctor` / `audit()` for authorisation and audit. Production: add Alembic first.

## 2. Show it on the dashboard
`dashboard/service.py::_query` joins from images; add an outer join on `ClinicalRecord` via `Screening.id`, or fetch it
lazily in the image-detail response. The queue contract (`QueueItem`) can gain fields without breaking clients.

## 3. Fusion model later
- Per-image outputs already stored: calibrated probabilities (`predictions.disease_probs`) and the 768-d embedding
  (`predictions.embedding`, float32 bytes). The model card warns embeddings of the image model's *own training images* are
  over-confident: fit the fusion model on data the image model has not seen.
- Implement a new protocol keyed on a **screening** (images + clinical record -> result) next to `inference/protocol.py`,
  store results in a new table keyed by `screening_id` (+ model tag/hash, as `Prediction` does), and review them with the
  same append-only review pattern.
- `ImageModel` (image path -> `FundusPrediction`) stays the interface for per-image models; swap implementations via
  `create_app(engine_loader=...)`.
