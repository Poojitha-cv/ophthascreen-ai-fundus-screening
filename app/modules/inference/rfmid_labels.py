"""RFMiD abnormality code -> full name.

Source of the CODES: the `RFMiD_Training_Labels.csv` header (45 abnormality columns after `ID` and `Disease_Risk`),
which also equals `disease_cols` in models/<tag>/inference_config.json.
Source of the NAMES: the RFMiD dataset paper (Pachade et al., "Retinal Fundus Multi-Disease Image Dataset (RFMiD):
A Dataset for Multi-Disease Detection Research", Data 2021) - the CSV itself carries codes only.

Names are the dataset's own labels; nothing here is re-interpreted (e.g. ODC is Optic Disc Cupping, NOT glaucoma).
`Disease_Risk` is deliberately NOT in this table: it is the separate abnormal-vs-normal output, not an abnormality.
"""
from __future__ import annotations

RFMID_NAMES: dict[str, str] = {
    "DR": "Diabetic Retinopathy",
    "ARMD": "Age-Related Macular Degeneration",
    "MH": "Media Haze",
    "DN": "Drusen",
    "MYA": "Myopia",
    "BRVO": "Branch Retinal Vein Occlusion",
    "TSLN": "Tessellation",
    "ERM": "Epiretinal Membrane",
    "LS": "Laser Scars",
    "MS": "Macular Scar",
    "CSR": "Central Serous Retinopathy",
    "ODC": "Optic Disc Cupping",
    "CRVO": "Central Retinal Vein Occlusion",
    "TV": "Tortuous Vessels",
    "AH": "Asteroid Hyalosis",
    "ODP": "Optic Disc Pallor",
    "ODE": "Optic Disc Edema",
    "ST": "Shunt",
    "AION": "Anterior Ischemic Optic Neuropathy",
    "PT": "Parafoveal Telangiectasia",
    "RT": "Retinal Traction",
    "RS": "Retinitis",
    "CRS": "Chorioretinitis",
    "EDN": "Exudation",
    "RPEC": "Retinal Pigment Epithelium Changes",
    "MHL": "Macular Hole",
    "RP": "Retinitis Pigmentosa",
    "CWS": "Cotton Wool Spots",
    "CB": "Coloboma",
    "ODPM": "Optic Disc Pit Maculopathy",
    "PRH": "Preretinal Hemorrhage",
    "MNF": "Myelinated Nerve Fibers",
    "HR": "Hemorrhagic Retinopathy",
    "CRAO": "Central Retinal Artery Occlusion",
    "TD": "Tilted Disc",
    "CME": "Cystoid Macular Edema",
    "PTCR": "Post Traumatic Choroidal Rupture",
    "CF": "Choroidal Folds",
    "VH": "Vitreous Hemorrhage",
    "MCA": "Macroaneurysm",
    "VS": "Vasculitis",
    "BRAO": "Branch Retinal Artery Occlusion",
    "PLQ": "Plaque",
    "HPED": "Hemorrhagic Pigment Epithelial Detachment",
    "CL": "Collateral",
}

RISK_COLUMN = "Disease_Risk"   # separate abnormal-vs-normal output; never shown as an abnormality

NO_FLAG_MESSAGE = "No significant abnormality flagged"
REVIEW_MESSAGE = "Doctor review recommended"
BELOW_MESSAGE = "Below screening threshold"


def disease_name(code: str) -> str | None:
    return RFMID_NAMES.get(code)
