"""Quality checker behaviour on synthetic images. Thresholds are unvalidated defaults; these tests check that
each check fires on the condition it is named for and that metrics move in the right direction."""
import numpy as np
from PIL import Image

from app.core.config import QualityThresholds
from app.modules.imaging.quality import assess_quality
from tests.conftest import fundus_like

T = QualityThresholds()


def codes(rep):
    return {i["code"] for i in rep["issues"]}


def test_clean_image_passes():
    rep = assess_quality(fundus_like(), T)
    assert rep["status"] == "pass", rep
    assert rep["checker_version"] and rep["metrics"]["fov_fraction"] > 0.4


def test_black_image_fails_no_fundus():
    rep = assess_quality(Image.new("RGB", (1000, 1000), (0, 0, 0)), T)
    assert rep["status"] == "fail" and "no_fundus_region" in codes(rep)


def test_non_fundus_photo_gets_colour_warning():
    arr = np.random.default_rng(1).integers(40, 200, size=(900, 900, 3)).astype(np.uint8)
    arr[..., 0] = 60  # blue/green-ish noise frame: red channel suppressed
    rep = assess_quality(Image.fromarray(arr), T)
    assert "unusual_colour_profile" in codes(rep)


def test_too_small_fails():
    rep = assess_quality(fundus_like(size=(300, 300)), T)
    assert rep["status"] == "fail" and "too_small" in codes(rep)


def test_dark_and_overexposed():
    assert "dark" in codes(assess_quality(fundus_like(brightness=0.2), T))
    assert "too_dark" in codes(assess_quality(fundus_like(brightness=0.1), T))
    # darker still: nothing exceeds the background threshold, so it is reported as an empty frame (also a hard fail)
    assert assess_quality(fundus_like(brightness=0.05), T)["status"] == "fail"
    over = assess_quality(fundus_like(brightness=2.0), T)
    assert {"overexposed", "saturated_pixels"} & codes(over)


def test_blur_lowers_sharpness_and_warns():
    sharp = assess_quality(fundus_like(seed=3), T)
    blurred = assess_quality(fundus_like(seed=3, blur=14), T)
    assert blurred["metrics"]["sharpness_lapvar"] < sharp["metrics"]["sharpness_lapvar"] / 5
    assert "blurry" in codes(blurred) and "blurry" not in codes(sharp)


def test_cut_off_field_warns():
    im = fundus_like(size=(1200, 1000))
    cropped = im.crop((0, 0, 1200, 380))  # only a thin strip of the disc remains
    assert "fundus_field_cut_off" in codes(assess_quality(cropped, T))


def test_thresholds_are_configurable():
    strict = QualityThresholds(blur_lapvar_warn=1e9)
    assert "blurry" in codes(assess_quality(fundus_like(), strict))
