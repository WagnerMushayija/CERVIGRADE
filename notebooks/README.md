# Notebooks: where to find what

Every notebook here was run on Kaggle (GPU for training). Folders follow the order of the work. The row numbers are from `docs/Experiments_Log.md`.

## Quick lookup: "which notebook did this?"

| If you are asked about | Open this notebook | Log row |
|---|---|---|
| Where the three datasets came from, class counts, the split | `01_data/CerviGrade_Dataset_Acquisition_Kaggle.ipynb` | 1 |
| Stage 1: three classifiers on SIPaKMeD | `02_classifiers/CerviGrade_Training_Phase2_Kaggle.ipynb` | 2 |
| Stage 2: EfficientNetB0, ConvNeXt, RegNet on CRIC | `02_classifiers/stage2_cnn_models_cric.ipynb` (first runs), `02_classifiers/cnn_retrain_three_seeds.ipynb` (final, 3 seeds) | 3, 4 |
| PLIP (pathology model) with a linear classifier | `02_classifiers/plip_linear_probe.ipynb` | 5 |
| Undersampling the Negative cells | `02_classifiers/cnn_undersampling.ipynb` | 12 |
| Averaging saved predictions, confusion matrix, crop size | `02_classifiers/cnn_crop_experiments.ipynb` | 13, 14 |
| Attention head, learning rate / dropout sweep, 5-fold | `02_classifiers/cnn_attention_tuning_kfold.ipynb` | 16 |
| How the boxes were made, detector training (stage 1 and 2, oversampling) | `03_detector/bounding_boxes_and_detector_training.ipynb` | 1, 6, 7, 8 |
| Detector IoU on the test crops | `03_detector/detector_iou.ipynb` | 7b |
| Detector on whole CRIC slides | `03_detector/cric_field_test.ipynb` | 9 |
| Detector plus CNN on CRIC slides | `04_pipeline_tests/detector_plus_cnn.ipynb` | 11 |
| Finished pipeline on Mendeley photos | `04_pipeline_tests/mendeley_pipeline_test.ipynb` (the app-pipeline check is also `src/evaluation/mendeley_pipeline_check.py`) | 10a, 10b |
| Grouping the grades (three tiers, four classes), SCC after grouping | `05_analysis/grouping_check.ipynb` | 15 |
| Grad-CAM deletion test | Not a notebook yet (see the log, row 17) | 17 |
| Software tests | `src/app/backend/tests/` | 18 |

## Folders

- `01_data` - dataset preparation.
- `02_classifiers` - everything that trains or compares the cell classifiers.
- `03_detector` - box making, detector training, IoU, detector on whole slides.
- `04_pipeline_tests` - the detector and classifier used together, and on other data.
- `05_analysis` - analysis of saved results, nothing retrained.
- `archive` - the earlier assignment notebook (`ModelNotebook.ipynb`) and the script that built it. Kept for the record, not used by the results.

## Notes

- `detector_iou.ipynb` and `grouping_check.ipynb` were two halves of one Kaggle notebook called "IoU notebook". They were split here so each result has its own file. The outputs are as Kaggle printed them.
- `grouping_check.ipynb` reads the nine `probs_*.npz` files saved by the retrain (Kaggle dataset "Re trained models"). Nothing is retrained.
- The IoU "true" boxes come from our own segmentation, not from pathologists.
- Some Kaggle notebook titles differ from the file names here: "CNN + Detector" is `detector_plus_cnn`, "PLIP Models" is `plip_linear_probe`, "CerviGrade_Training_Stage2 CNN Models" is `stage2_cnn_models_cric`.
