# """Application settings. Env prefix OPH_, nested values use '__' (e.g. OPH_QUALITY__BLUR_LAPVAR_WARN=3)."""
# from __future__ import annotations

# import logging
# import secrets
# from functools import lru_cache
# from pathlib import Path
# from typing import Literal

# from pydantic import BaseModel, model_validator
# from pydantic_settings import BaseSettings, SettingsConfigDict

# log = logging.getLogger(__name__)


# class QualityThresholds(BaseModel):
#     """Heuristic image-quality thresholds.

#     UNVALIDATED defaults: there was no labelled image-quality data in the project bundle.
#     Only objectively unusable images (too small, no fundus region, almost black) are hard
#     failures; everything else is a warning. Calibrate on your own cameras with
#     scripts/quality_stats.py before relying on these.
#     """

#     min_side_px: int = 512                # shorter image side below this -> fail (model works at 512 internally)
#     work_size: int = 512                  # metrics are computed on a copy resized to this longest side
#     bg_threshold: int = 15                # same background threshold the model's crop step uses
#     min_fov_fraction_fail: float = 0.15   # fundus area / image area below this -> fail
#     fov_aspect_range: tuple[float, float] = (0.75, 1.33)  # fundus bbox w/h outside -> warn (cut off / not circular)
#     dark_mean_fail: float = 15.0          # mean luminance inside fundus below this -> fail
#     dark_mean_warn: float = 40.0
#     bright_mean_warn: float = 200.0
#     saturated_fraction_warn: float = 0.10  # share of fundus pixels with a channel >= 250
#     contrast_std_warn: float = 20.0       # std of green channel inside fundus
#     blur_lapvar_warn: float = 5.0         # variance of Laplacian (green, eroded mask, at work_size)
#     erosion_px: int = 10                  # keeps the fundus rim out of the sharpness estimate
#     red_green_ratio_warn: float = 1.0     # mean R / mean G below this -> warn (may not be a colour fundus photo)


# class Settings(BaseSettings):
#     model_config = SettingsConfigDict(env_file=".env", env_prefix="OPH_", env_nested_delimiter="__", extra="ignore")

#     env: Literal["development", "production", "test"] = "development"
#     database_url: str = "sqlite:///./data/app.db"
#     cors_origins: list[str] = []

#     # Auth
#     secret_key: str = ""
#     jwt_algorithm: str = "HS256"
#     access_token_minutes: int = 60
#     login_max_failures: int = 5
#     login_lockout_minutes: int = 15

#     # Image storage / upload limits
#     storage_dir: Path = Path("data/images")
#     max_upload_bytes: int = 25 * 1024 * 1024
#     max_image_pixels: int = 100_000_000

#     # Model
#     model_dir: Path = Path("models/convnext_tiny_v1")
#     model_device: str | None = None
#     require_model: bool = False

#     # Policy
#     patient_can_see_ai_results: bool = False

#     quality: QualityThresholds = QualityThresholds()

#     @model_validator(mode="after")
#     def _check_secret(self) -> "Settings":
#         if self.env == "production":
#             if len(self.secret_key) < 32:
#                 raise ValueError("OPH_SECRET_KEY must be set (>= 32 chars) when OPH_ENV=production")
#         elif not self.secret_key:
#             self.secret_key = secrets.token_urlsafe(48)
#             log.warning("OPH_SECRET_KEY not set: using an ephemeral key; all tokens become invalid on restart.")
#         return self


# @lru_cache
# def get_settings() -> Settings:
#     return Settings()



"""Application settings. Env prefix OPH_, nested values use '__' (e.g. OPH_QUALITY__BLUR_LAPVAR_WARN=3)."""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class QualityThresholds(BaseModel):
    """Heuristic image-quality thresholds.

    UNVALIDATED defaults: there was no labelled image-quality data in the project bundle.
    Only objectively unusable images (too small, no fundus region, almost black) are hard
    failures; everything else is a warning. Calibrate on your own cameras with
    scripts/quality_stats.py before relying on these.
    """

    min_side_px: int = 512                # shorter image side below this -> fail (model works at 512 internally)
    work_size: int = 512                  # metrics are computed on a copy resized to this longest side
    bg_threshold: int = 15                # same background threshold the model's crop step uses
    min_fov_fraction_fail: float = 0.15   # fundus area / image area below this -> fail
    fov_aspect_range: tuple[float, float] = (0.75, 1.33)  # fundus bbox w/h outside -> warn (cut off / not circular)
    dark_mean_fail: float = 15.0          # mean luminance inside fundus below this -> fail
    dark_mean_warn: float = 40.0
    bright_mean_warn: float = 200.0
    saturated_fraction_warn: float = 0.10  # share of fundus pixels with a channel >= 250
    contrast_std_warn: float = 20.0       # std of green channel inside fundus
    blur_lapvar_warn: float = 5.0         # variance of Laplacian (green, eroded mask, at work_size)
    erosion_px: int = 10                  # keeps the fundus rim out of the sharpness estimate
    red_green_ratio_warn: float = 1.0     # mean R / mean G below this -> warn (may not be a colour fundus photo)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OPH_", env_nested_delimiter="__", extra="ignore")

    env: Literal["development", "production", "test"] = "development"
    database_url: str = "sqlite:///./data/app.db"
    cors_origins: list[str] = []

    # Auth
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # Image storage / upload limits
    storage_dir: Path = Path("data/images")
    max_upload_bytes: int = 25 * 1024 * 1024
    max_image_pixels: int = 100_000_000

    # Model
    model_dir: Path = Path("models/convnext_tiny_v1")
    model_device: str | None = None
    require_model: bool = False
    gradcam_cache_items: int = 64         # in-memory LRU of rendered attention maps (0 = no caching)

    # Policy
    patient_can_see_ai_results: bool = False

    quality: QualityThresholds = QualityThresholds()

    @model_validator(mode="after")
    def _check_secret(self) -> "Settings":
        if self.env == "production":
            if len(self.secret_key) < 32:
                raise ValueError("OPH_SECRET_KEY must be set (>= 32 chars) when OPH_ENV=production")
        elif not self.secret_key:
            self.secret_key = secrets.token_urlsafe(48)
            log.warning("OPH_SECRET_KEY not set: using an ephemeral key; all tokens become invalid on restart.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
