import json, sys
from PIL import Image
from app.core.config import QualityThresholds
from app.modules.imaging.quality import assess_quality

path = sys.argv[1]
with Image.open(path) as im:
    rep = assess_quality(im, QualityThresholds())

print("status:", rep["status"])
print("issues:", [i["code"] for i in rep["issues"]])
print(json.dumps(rep["metrics"], indent=2))