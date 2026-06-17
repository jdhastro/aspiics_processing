# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based pipeline for processing ASPIICS (Association of Spacecraft for Polarimetric and Imaging Investigation of the Corona of the Sun) coronagraph images. It produces calibrated solar corona images from raw Level-1 FITS data through two processing stages: L2 (detector calibration) and L3 (science products).

## Setup

```bash
uv venv
.venv\Scripts\activate   # Windows
# or: source .venv/bin/activate  (Linux/Mac)
uv sync
```

Calibration data from the [ASPIICS calibration data release 1.0](https://gitlab-as.oma.be/P3SC/p3sc_calibration_data_repository/-/releases) must be placed in `calibration-data/`.

## Running the Processors

**Batch processing (primary workflow):** Use the Jupyter notebooks:
- `process_l2_batch.ipynb` — batch L2 processing with multithreading
- `process_l3_batch.ipynb` — batch L3 processing

**Single file L2 processing:**
```bash
cd l2_processor
python l2_master.py <input_l1.fits> [options]
# Key options:
#   --banding_correction     apply column banding correction
#   --outdir <path>          output directory (default: ./output/)
#   --filter <name>          override filter ("Fe XIV", "He I", "Wideband", "Polarizer 0/60/120")
#   -C <config.json>         use alternate calibration config (default: calibr_data.json)
```

**Single file L3 processing:**
```bash
cd l3_processor
python l3_merge.py <file_short.fits> [<file_med.fits>] [<file_long.fits>] [options]
# Key options:
#   --soft_merge             30px smooth blending at exposure transitions
#   --center                 re-center/de-rotate images (default: True)
#   --coalign                co-align images to longest exposure
#   --outdir <path>
```

Other L3 scripts (`l3_fcorona.py`, `l3_onband.py`, `l3_polariz.2.py`) are standalone CLI scripts for F-corona subtraction, on-band processing, and polarimetry.

## Architecture

### Processing Stages

**L2 (detector calibration) — `l2_processor/`:**
- `l2_master.py` — top-level script; reads L1 FITS, applies calibration steps in order: bias → gain → nonlinearity correction → dark current → flat field → optional banding correction → hot pixel replacement → saturation masking → radiometric calibration to MSB units
- `aspiics_detector.py` — calibration functions (bias, dark current, flat field, nonlinearity, hot pixels, banding correction); all functions take `(header, params)` where `params` is loaded from the JSON config
- `banding_denoise.py` — multipass column banding correction algorithm; uses median and non-local means filtering to isolate and subtract column-to-column variations without removing coronal structures; supports odd/even row splitting to account for sensor readout architecture
- `aspiics_optics.py` — vignetting, diffraction, ghost, and scattering corrections (optical path)
- `aspiics_get_opse.py` — OPSE (On-board Photometric and Star Estimation) LED position detection
- `parameters.py` — loads JSON calibration config into a dict

**L3 (science products) — `l3_processor/`:**
- `l3_merge.py` — merges 1–3 L2 images at different exposure times into a single HDR image; optionally re-centers/de-rotates (using WCS keywords) and applies soft blending at saturation boundaries
- `aspiics_misc.py` — shared utilities: FITS I/O, `soft_merge()` (distance-transform-based alpha blending), `nan_affine_transform()` (NaN-aware affine warp with prefilter for sharpness), `rotate_center1()` and `shift_image()` for WCS-based image alignment
- `l3_fcorona.py` — F-corona model (Allen 1977 or Koutchmy 2000) subtraction
- `l3_onband.py` — on-band coronal emission processing
- `l3_polariz.2.py` — polarimetric processing from three polarizer images

### Configuration

`l2_config.json` (root directory) — the primary calibration config used by the batch notebooks. It specifies:
- Paths to calibration files relative to the project root (bias, dark, flat, nonlinearity, hot pixels, vignetting)
- Per-filter radiometric parameters (Aphot, MSB, CONV_PHO, Photon_energy, x_IO, y_IO)
- Detector parameters (gain, readout noise, IO position, pixel scale)

### Key Data Flow

1. L1 FITS (raw DN, integer) → L2 FITS (calibrated, float32, units: MSB = Mean Solar Brightness)
2. Multiple L2 exposures (short/medium/long) → L3 FITS (merged, re-centered, float32)
3. FITS headers carry WCS keywords (CRPIX1/2, CRVAL1/2, CROTA, PC matrix) used for image alignment and IO/LED position tracking through transforms

### NaN/Inf conventions

- NaN = bad/masked pixels (originally BLANK values or non-finite after calibration)
- Inf = saturated/overexposed pixels (set after nonlinearity correction detects values beyond the LUT range)
- Both are tracked through all transforms and restored after affine warps

### Scripts run from their own directory

`l2_master.py` and all `l3_processor/` scripts use relative paths and must be run from within their respective subdirectory, or the batch notebooks handle `os.chdir` for them.
