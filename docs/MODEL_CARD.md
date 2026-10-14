# Fundus-image component - ConvNeXt-Tiny on RFMiD (`convnext_tiny_v1`)

**Status: research prototype. Not a medical device, not clinically validated, not for diagnosis or patient care.**
All numbers below are read from the saved result files of this notebook (single training run, single official split, one seed).

## 1. Intended use
* Fundus-image component of a later multimodal ophthalmic screening research system: (a) abnormal-vs-normal screening score, (b) multi-label disease probabilities for the frequent classes, (c) a confidence / review flag, (d) a 768-d image embedding for fusion.
* Not intended: stand-alone diagnosis, use on other camera types or populations without re-validation, detection of rare conditions (see Limitations).

## 2. Data - what was verified in the notebook, and how it compares with the paper
* Dataset: Kaggle `andrewmvd/retinal-disease-classification`. It is the RFMiD dataset described in the uploaded paper (Pachade et al., Data 2021), not MuReD; we never assumed otherwise.
* 3200 PNG images with the official split used unchanged: train 1920 / validation 640 / test 640 (matches the paper). Labels: `Disease_Risk` plus 45 disease columns (multi-label; about 30% of abnormal images carry more than one disease). `Disease_Risk` equals "any disease" on every row.
* Per-class totals (46 incl. normal) match paper Table 3 exactly. Labels were re-read from the original CSVs and matched row by row to the cached arrays.
* **Difference from the paper:** cameras identified from image resolution give TOPCON 3D OCT-2000 = 2427, Kowa VX-10a = 497, TOPCON TRC-NW300 = 276, versus paper Table 2: 2427 / 467 / 306. The reason is unknown.
* Abnormal prevalence is 79.1% in every split. This is a property of the dataset, not of a screening population; precision, accuracy and PPV would be lower at realistic prevalence.
* Abnormal share differs strongly by camera in training (TRC-NW300: 30% abnormal; Kowa: 75%; TOPCON OCT-2000: 85%).
* Classes evaluable (>=1 positive): 43/45 in train, 39/45 in validation, 36/45 in test.
* **Leakage:** IDs restart in each split, but no exact duplicate file exists (MD5 within and across splits). A vessel-structure near-duplicate check was inconclusive: its positive controls re-found only about 30% of moderately perturbed copies. There are no patient IDs, so same-patient (left/right eye, repeat visit) leakage cannot be excluded. "Leakage-free" is therefore claimed only for: official split, no exact duplicates, no evidence of near-duplicates found by a weak check.
* Source: single-centre data collected in India (per the paper), 2009-2020, three cameras.

## 3. Model and training
* Backbone `convnext_tiny.fb_in22k_ft_in1k` (ImageNet-22k pre-trained, fine-tuned end to end), 46 sigmoid outputs, binary cross-entropy, input 384x384, ImageNet mean/std.
* Preprocessing: crop black border (threshold 15), pad to square, Lanczos resize to 512, then bilinear (anti-aliased) resize to 384.
* Augmentation (GPU, train only): horizontal flip, rotation +/-20 deg, scale +/-10%, translation +/-5%, brightness/contrast/gamma/per-channel gain, black background preserved.
* Class imbalance: repeat-factor sampling (T=0.05, cap 8x), train images only.
* Optimiser AdamW (lr backbone 0.0001, head 0.0005, weight decay 0.05), cosine schedule with 1 warm-up epoch, 30 epochs, batch 32, fp16 AMP, drop 0.2, drop-path 0.1, seed 42.
* Checkpoint chosen on validation only: epoch 15 (score = 0.5 x Disease_Risk AUROC + 0.5 x mAP over the 21 diseases with >=5 validation positives = the "core" classes). Temperature 1.65, all thresholds and the review cutoff were also fitted on validation only. The test set was evaluated once, after freezing everything.

## 4. Decision rules
* Disease_Risk: max-F1 threshold 0.475; screening threshold 0.108 (validation sensitivity >= 95%).
* Disease flags only for the 21 core classes: per-class thresholds for 11 classes with >=15 validation positives, otherwise global 0.25. Other classes: probabilities only, not validated.
* `needs_review` = Disease_Risk confidence |logit(p) - logit(thr)| < 2.570 (the least-confident 20% on validation) or failed border crop.

## 5. Test results (640 images, frozen)
**Disease_Risk (abnormal vs normal):** AUROC 0.984 (95% CI 0.976-0.991); PR-AUC 0.996 (95% CI 0.994-0.998) (constant-predictor AP = 0.791).

| operating point | threshold | accuracy | sensitivity | specificity | precision | F1 |
|---|---|---|---|---|---|---|
| max-F1 | 0.475 | 0.933 | 0.923 | 0.970 | 0.992 | 0.956 |
| screening | 0.107 | 0.950 | 0.966 | 0.888 | 0.970 | 0.968 |

Majority-class accuracy is 0.791. Per camera:

| camera | n | abnormal | AUROC | sens@maxF1 | spec@maxF1 | sens@screen | spec@screen |
|---|---|---|---|---|---|---|---|
| Kowa_VX10a | 128 | 78 | 0.992 | 0.872 | 1.000 | 0.949 | 0.980 |
| TOPCON_3D_OCT2000 | 439 | 407 | 0.983 | 0.958 | 0.906 | 0.985 | 0.719 |
| TOPCON_TRC_NW300 | 73 | 21 | 0.821 | 0.429 | 0.981 | 0.667 | 0.904 |

**Diseases (21 core classes, chosen on validation):** macro-AUROC 0.949 (95% CI 0.935-0.961); mAP 0.597 (95% CI 0.567-0.662); macro-F1 0.524 (95% CI 0.469-0.571) at the frozen primary thresholds (macro-precision 0.586, macro-recall 0.510; micro-F1 0.670; at a plain 0.5 threshold macro-F1 0.503, micro-F1 0.690). Exact-match accuracy over all 45 disease columns: 0.545. CIs resample images and ignore possible patient clustering.

Per-class test metrics for the core classes (classes with fewer than about 10 test positives are noisy; the full 45-class table is in `results/test/per_class_test_metrics.csv`, 9 classes have no test positive and cannot be evaluated):

| cls | train_pos | test_pos | AUROC | AP | thr | precision | recall | F1 |
|---|---|---|---|---|---|---|---|---|
| DR | 376 | 124 | 0.984 | 0.950 | 0.750 | 0.948 | 0.742 | 0.833 |
| MH | 317 | 104 | 0.972 | 0.899 | 0.250 | 0.681 | 0.904 | 0.777 |
| ODC | 282 | 91 | 0.905 | 0.725 | 0.275 | 0.746 | 0.516 | 0.610 |
| TSLN | 186 | 53 | 0.965 | 0.711 | 0.400 | 0.648 | 0.660 | 0.654 |
| DN | 138 | 46 | 0.918 | 0.600 | 0.275 | 0.452 | 0.717 | 0.555 |
| MYA | 101 | 32 | 0.994 | 0.934 | 0.450 | 0.893 | 0.781 | 0.833 |
| ARMD | 100 | 31 | 0.949 | 0.672 | 0.300 | 0.538 | 0.677 | 0.600 |
| ODP | 65 | 24 | 0.854 | 0.409 | 0.275 | 0.357 | 0.417 | 0.385 |
| BRVO | 73 | 23 | 0.937 | 0.805 | 0.575 | 0.783 | 0.783 | 0.783 |
| ODE | 58 | 17 | 0.958 | 0.839 | 0.825 | 0.929 | 0.765 | 0.839 |
| LS | 47 | 15 | 0.929 | 0.747 | 0.550 | 0.818 | 0.600 | 0.692 |
| RS | 43 | 14 | 0.995 | 0.805 | 0.250 | 0.750 | 0.643 | 0.692 |
| CSR | 37 | 13 | 0.966 | 0.603 | 0.250 | 0.714 | 0.385 | 0.500 |
| CRS | 32 | 11 | 0.968 | 0.458 | 0.250 | 0.500 | 0.273 | 0.353 |
| CRVO | 28 | 9 | 0.983 | 0.772 | 0.250 | 0.750 | 0.667 | 0.706 |
| MS | 15 | 7 | 0.921 | 0.275 | 0.250 | 0.333 | 0.286 | 0.308 |
| ERM | 14 | 5 | 0.901 | 0.124 | 0.250 | 0.125 | 0.200 | 0.154 |
| RT | 14 | 5 | 0.995 | 0.789 | 0.250 | 1.000 | 0.200 | 0.333 |
| RPEC | 22 | 4 | 0.957 | 0.111 | 0.250 | 0.100 | 0.250 | 0.143 |
| AION | 17 | 4 | 0.920 | 0.072 | 0.250 | 0.000 | 0.000 | 0.000 |
| EDN | 15 | 4 | 0.957 | 0.231 | 0.250 | 0.250 | 0.250 | 0.250 |

## 6. Confidence and calibration (test)
* Temperature scaling fitted on validation improves pooled core-disease ECE from 0.017 to 0.006. The Disease_Risk probability stays only roughly calibrated (ECE 0.065).
* Distance from the threshold detects Disease_Risk errors with AUROC 0.894. TTA disagreement gave no additional information and TTA is not used.
* Review rule (fixed on validation): flags 17.8% of test images; error rate 1.9% on unflagged vs 28.9% on flagged images; catches 33 of 43 errors.
* Disease-level: 57.0% of test images have all 21 core columns correct; precision of predicted positives rises from about 0.27 (p 0.25-0.5) to about 0.91 (p >= 0.9).

## 7. Explainability (Grad-CAM, qualitative)
Last-stage Grad-CAM (12x12 map at 384 px, so coarse). Randomised-weights control: mean correlation with trained maps 0.08 (typical cases), -0.18 (false positives), except ODC/ODE, where the map sits on the bright optic disc. Border-mass ratio about 1.0 (random-init 0.77); 13 of 640 images above 2.0. No lesion annotations exist, so localisation is not validated and the maps are not evidence of clinically correct reasoning.

## 8. Known failure modes (test)
* Single-label ODC: 18 images, caught 22.2% at the max-F1 and 55.6% at the screening threshold. Single-label ODP: 12 images, 50.0% / 83.3%. These two classes account for most Disease_Risk misses.
* TRC-NW300: Disease_Risk sensitivity is lowest on this camera (table above; only 21 abnormal test images). Its abnormal training images are dominated by ODC and MH, so camera effects and the ODC weakness cannot be separated; a camera shortcut is neither confirmed nor excluded.
* Most disease false positives occur on images that truly carry another disease (systematic confusions include MYA->TSLN, CSR->DN, MS->ARMD, DN->MH); whether some reflect incomplete labels cannot be determined here.
* Rare classes are essentially not detected:

| tier | true_labels | in_top3 | flagged |
|---|---|---|---|
| 0-4 train positives | 15 | 0.133 | 0.000 |
| 5-19 train positives | 43 | 0.395 | 0.233 |
| 20+ train positives | 611 | 0.879 | 0.689 |

## 9. Limitations
* One dataset, one centre, three cameras, one split, one seed; no external validation; thresholds were tuned on a small validation set, so operating points may shift.
* The paper states labels used clinical records and visual fields; some labels (e.g. ODC) may not be fully determinable from a photograph.
* Prevalence (79% abnormal) is unrepresentative of screening populations.
* 9 of 45 classes have no test positive; 15 more have 3 or fewer. Performance on them is unknown or anecdotal.
* Patient-level leakage cannot be excluded (no patient IDs).
* Software: torch 2.10.0+cu128, timm 1.0.26, torchvision 0.25.0+cu128.

## 10. Interface for multimodal fusion
`model/fundus_inference.py` -> `FundusScreener(export_dir).predict(images, return_embedding=True)` returns per image: `risk_prob`, two abnormal flags, `risk_confidence`, `needs_review`, `flagged_diseases` (core classes), `disease_probs` (45), `embedding` (768-d float32, the pre-logit feature). Fuse the calibrated probabilities and/or embedding with other modalities using training data the image model has not been fitted on (otherwise its embeddings on its own training images are over-confident), and carry `needs_review` forward as an uncertainty signal.

## 11. Files
`model/` deployable export (weights, inference_config.json, fundus_inference.py, manifest); `checkpoints/` full checkpoint with validation metrics; `results/` test metrics, predictions, uncertainty, Grad-CAM, error analysis, figures, training history, calibration; `docs/` this card, README, environment, notebook cell source.
