"""
ASPIICS Processing GUI
Desktop interface for L2 and L3 processing pipelines.
"""
import sys
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QTextEdit, QFileDialog, QDoubleSpinBox, QSizePolicy,
    QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, QProcess, QProcessEnvironment
from PySide6.QtGui import QFont, QTextCursor, QColor

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
L2_DIR = SCRIPT_DIR / "l2_processor"
L3_DIR = SCRIPT_DIR / "l3_processor"
PYTHON = sys.executable


def _browse_file(parent, line_edit, caption, filter_str="FITS Files (*.fits *.fit);;All Files (*)"):
    path, _ = QFileDialog.getOpenFileName(parent, caption, "", filter_str)
    if path:
        line_edit.setText(path)


def _browse_dir(parent, line_edit, caption):
    path = QFileDialog.getExistingDirectory(parent, caption, "")
    if path:
        line_edit.setText(path)


def _section_label(text):
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    return lbl


# ---------------------------------------------------------------------------
# Log widget
# ---------------------------------------------------------------------------

class LogWidget(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet("background:#1e1e1e; color:#d4d4d4;")

    def append_stdout(self, text):
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.End)

    def append_stderr(self, text):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(QColor("#f48771"))
        cursor.insertText(text, fmt)
        self.moveCursor(QTextCursor.MoveOperation.End)

    def append_info(self, text):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(QColor("#4ec9b0"))
        cursor.insertText(text + "\n", fmt)
        self.moveCursor(QTextCursor.MoveOperation.End)


# ---------------------------------------------------------------------------
# Process runner mixin
# ---------------------------------------------------------------------------

class ProcessRunner:
    """Mixin that provides QProcess-based script execution."""

    def _init_process(self):
        self._proc = None

    def _run_script(self, script_path: Path, args: list, cwd: Path, log: LogWidget, run_btn: QPushButton):
        if self._proc and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
            return

        log.clear()
        log.append_info(f"Running: {PYTHON} {script_path.name} {' '.join(args)}")
        log.append_info(f"CWD: {cwd}\n")

        self._proc = QProcess()
        self._proc.setWorkingDirectory(str(cwd))

        env = QProcessEnvironment.systemEnvironment()
        existing = env.value("PYTHONPATH", "")
        env.insert("PYTHONPATH", str(cwd) + (";" + existing if existing else ""))
        self._proc.setProcessEnvironment(env)

        self._proc.readyReadStandardOutput.connect(
            lambda: log.append_stdout(self._proc.readAllStandardOutput().data().decode("utf-8", errors="replace"))
        )
        self._proc.readyReadStandardError.connect(
            lambda: log.append_stderr(self._proc.readAllStandardError().data().decode("utf-8", errors="replace"))
        )
        self._proc.finished.connect(lambda code, _: self._on_finished(code, run_btn, log))
        self._proc.errorOccurred.connect(lambda err: log.append_stderr(f"\nProcess error: {err}\n"))

        run_btn.setText("Stop")
        self._proc.start(PYTHON, [str(script_path)] + args)

    def _on_finished(self, exit_code, run_btn: QPushButton, log: LogWidget):
        run_btn.setText(self._run_label)
        if exit_code == 0:
            log.append_info(f"\nFinished successfully (exit 0).")
        else:
            log.append_stderr(f"\nExited with code {exit_code}.")


# ---------------------------------------------------------------------------
# L2 Processing tab
# ---------------------------------------------------------------------------

class L2Tab(QWidget, ProcessRunner):
    _run_label = "Run L2 Processing"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_process()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        io_box = QGroupBox("Input")
        io_layout = QGridLayout(io_box)

        io_layout.addWidget(QLabel("L1 FITS file:"), 0, 0)
        self.input_file = QLineEdit()
        self.input_file.setPlaceholderText("Select input L1 FITS file …")
        io_layout.addWidget(self.input_file, 0, 1)
        btn_in = QPushButton("Browse…")
        btn_in.clicked.connect(lambda: _browse_file(self, self.input_file, "Select L1 FITS file"))
        io_layout.addWidget(btn_in, 0, 2)

        io_layout.addWidget(QLabel("Output directory:"), 1, 0)
        self.outdir = QLineEdit("./output/")
        io_layout.addWidget(self.outdir, 1, 1)
        btn_out = QPushButton("Browse…")
        btn_out.clicked.connect(lambda: _browse_dir(self, self.outdir, "Select output directory"))
        io_layout.addWidget(btn_out, 1, 2)

        io_layout.addWidget(QLabel("Calibration config:"), 2, 0)
        self.cal_file = QLineEdit("calibr_data.json")
        self.cal_file.setPlaceholderText("Default: calibr_data.json (inside l2_processor/)")
        io_layout.addWidget(self.cal_file, 2, 1)
        btn_cal = QPushButton("Browse…")
        btn_cal.clicked.connect(lambda: _browse_file(self, self.cal_file, "Select calibration JSON",
                                                      "JSON Files (*.json);;All Files (*)"))
        io_layout.addWidget(btn_cal, 2, 2)

        root.addWidget(io_box)

        opt_box = QGroupBox("Options")
        opt_layout = QGridLayout(opt_box)

        self.cb_banding = QCheckBox("Banding correction")
        opt_layout.addWidget(self.cb_banding, 0, 0)

        self.cb_mark_io = QCheckBox("Mark IO center")
        opt_layout.addWidget(self.cb_mark_io, 0, 1)

        self.cb_mark_sun = QCheckBox("Mark solar center")
        opt_layout.addWidget(self.cb_mark_sun, 0, 2)

        opt_layout.addWidget(QLabel("Force filter:"), 1, 0)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["(from header)", "Fe XIV", "He I", "Wideband",
                                     "Polarizer 0", "Polarizer 60", "Polarizer 120"])
        opt_layout.addWidget(self.filter_combo, 1, 1)

        opt_layout.addWidget(QLabel("Diffraction file:"), 2, 0)
        self.diff_file = QLineEdit()
        self.diff_file.setPlaceholderText("Optional — leave blank to skip")
        opt_layout.addWidget(self.diff_file, 2, 1)
        btn_diff = QPushButton("Browse…")
        btn_diff.clicked.connect(lambda: _browse_file(self, self.diff_file, "Select diffraction FITS"))
        opt_layout.addWidget(btn_diff, 2, 2)

        self.cb_save_diff = QCheckBox("Save diffraction file")
        opt_layout.addWidget(self.cb_save_diff, 3, 0)

        root.addWidget(opt_box)

        self.run_btn = QPushButton(self._run_label)
        self.run_btn.setFixedHeight(36)
        self.run_btn.setStyleSheet("font-weight:bold;")
        self.run_btn.clicked.connect(self._run)
        root.addWidget(self.run_btn)

        root.addWidget(QLabel("Log:"))
        self.log = LogWidget()
        root.addWidget(self.log, stretch=1)

    def _run(self):
        input_path = self.input_file.text().strip()
        if not input_path:
            QMessageBox.warning(self, "Missing input", "Please select an L1 FITS input file.")
            return

        args = [input_path]

        cal = self.cal_file.text().strip()
        if cal:
            args += ["-C", cal]

        outdir = self.outdir.text().strip()
        if outdir:
            args += ["--outdir", outdir]

        filt = self.filter_combo.currentText()
        if filt != "(from header)":
            args += ["--filter", filt]

        if self.cb_banding.isChecked():
            args.append("--banding_correction")
        if self.cb_mark_io.isChecked():
            args.append("--mark_IO")
        if self.cb_mark_sun.isChecked():
            args.append("--mark_suncenter")

        diff = self.diff_file.text().strip()
        if diff:
            args += ["-D", diff]
        if self.cb_save_diff.isChecked():
            args.append("--save_diff")

        self._run_script(L2_DIR / "l2_master.py", args, L2_DIR, self.log, self.run_btn)


# ---------------------------------------------------------------------------
# L3 Merge tab
# ---------------------------------------------------------------------------

class L3MergeTab(QWidget, ProcessRunner):
    _run_label = "Run L3 Merge"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_process()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        io_box = QGroupBox("Input L2 Files (1–3, ordered by exposure time)")
        io_layout = QGridLayout(io_box)

        labels = ["Short exposure:", "Medium exposure:", "Long exposure:"]
        self.file_edits = []
        for i, lbl in enumerate(labels):
            io_layout.addWidget(QLabel(lbl), i, 0)
            edit = QLineEdit()
            edit.setPlaceholderText("Optional" if i > 0 else "Required")
            self.file_edits.append(edit)
            io_layout.addWidget(edit, i, 1)
            btn = QPushButton("Browse…")
            btn.clicked.connect(lambda checked, e=edit: _browse_file(self, e, "Select L2 FITS file"))
            io_layout.addWidget(btn, i, 2)

        root.addWidget(io_box)

        out_box = QGroupBox("Output")
        out_layout = QGridLayout(out_box)
        out_layout.addWidget(QLabel("Output directory:"), 0, 0)
        self.outdir = QLineEdit("./output/")
        out_layout.addWidget(self.outdir, 0, 1)
        btn_out = QPushButton("Browse…")
        btn_out.clicked.connect(lambda: _browse_dir(self, self.outdir, "Select output directory"))
        out_layout.addWidget(btn_out, 0, 2)
        root.addWidget(out_box)

        opt_box = QGroupBox("Options")
        opt_layout = QGridLayout(opt_box)

        self.cb_center = QCheckBox("Re-center / de-rotate (default on)")
        self.cb_center.setChecked(True)
        opt_layout.addWidget(self.cb_center, 0, 0)

        self.cb_coalign = QCheckBox("Co-align images to longest exposure")
        opt_layout.addWidget(self.cb_coalign, 0, 1)

        self.cb_soft_merge = QCheckBox("Soft merge (30 px smooth transition)")
        opt_layout.addWidget(self.cb_soft_merge, 1, 0)

        self.cb_save_shifted = QCheckBox("Save shifted L2 images")
        opt_layout.addWidget(self.cb_save_shifted, 1, 1)

        crval_frame = QFrame()
        crval_layout = QHBoxLayout(crval_frame)
        crval_layout.setContentsMargins(0, 0, 0, 0)

        self.cb_force_crval1 = QCheckBox("Force CRVAL1 (arcsec):")
        self.crval1_spin = QDoubleSpinBox()
        self.crval1_spin.setRange(-9999, 9999)
        self.crval1_spin.setDecimals(2)
        self.crval1_spin.setEnabled(False)
        self.cb_force_crval1.toggled.connect(self.crval1_spin.setEnabled)
        crval_layout.addWidget(self.cb_force_crval1)
        crval_layout.addWidget(self.crval1_spin)
        crval_layout.addSpacing(16)

        self.cb_force_crval2 = QCheckBox("Force CRVAL2 (arcsec):")
        self.crval2_spin = QDoubleSpinBox()
        self.crval2_spin.setRange(-9999, 9999)
        self.crval2_spin.setDecimals(2)
        self.crval2_spin.setEnabled(False)
        self.cb_force_crval2.toggled.connect(self.crval2_spin.setEnabled)
        crval_layout.addWidget(self.cb_force_crval2)
        crval_layout.addWidget(self.crval2_spin)
        crval_layout.addStretch()

        opt_layout.addWidget(crval_frame, 2, 0, 1, 2)
        root.addWidget(opt_box)

        self.run_btn = QPushButton(self._run_label)
        self.run_btn.setFixedHeight(36)
        self.run_btn.setStyleSheet("font-weight:bold;")
        self.run_btn.clicked.connect(self._run)
        root.addWidget(self.run_btn)

        root.addWidget(QLabel("Log:"))
        self.log = LogWidget()
        root.addWidget(self.log, stretch=1)

    def _run(self):
        files = [e.text().strip() for e in self.file_edits if e.text().strip()]
        if not files:
            QMessageBox.warning(self, "Missing input", "Please select at least one L2 FITS file.")
            return

        args = files
        args += ["--outdir", self.outdir.text().strip() or "./output/"]

        if not self.cb_center.isChecked():
            args.append("--no-center")
        if self.cb_coalign.isChecked():
            args.append("--coalign")
        if self.cb_soft_merge.isChecked():
            args.append("--soft_merge")
        if self.cb_save_shifted.isChecked():
            args.append("--save_shifted")
        if self.cb_force_crval1.isChecked():
            args += ["--CRVAL1", str(self.crval1_spin.value())]
        if self.cb_force_crval2.isChecked():
            args += ["--CRVAL2", str(self.crval2_spin.value())]

        self._run_script(L3_DIR / "l3_merge.py", args, L3_DIR, self.log, self.run_btn)


# ---------------------------------------------------------------------------
# FITS Viewer tab
# ---------------------------------------------------------------------------

class FITSViewerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = None
        self._header = None
        self._source_path = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # File picker
        top = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Select a FITS file to view …")
        top.addWidget(self.file_edit)
        btn_open = QPushButton("Open FITS…")
        btn_open.clicked.connect(self._open_file)
        top.addWidget(btn_open)
        root.addLayout(top)

        # Display controls — row 1: scale, colormap, percentile clip
        ctrl1 = QHBoxLayout()
        ctrl1.addWidget(QLabel("Scale:"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["Linear", "Log", "Sqrt", "Asinh"])
        self.scale_combo.currentTextChanged.connect(self._on_scale_changed)
        ctrl1.addWidget(self.scale_combo)

        ctrl1.addSpacing(12)
        ctrl1.addWidget(QLabel("Colormap:"))
        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(["gray", "inferno", "hot", "viridis", "plasma", "magma"])
        self.cmap_combo.currentTextChanged.connect(self._redraw)
        ctrl1.addWidget(self.cmap_combo)

        ctrl1.addSpacing(12)
        ctrl1.addWidget(QLabel("Clip percentile:"))
        self.pct_lo = QDoubleSpinBox()
        self.pct_lo.setRange(0, 49.9)
        self.pct_lo.setValue(1.0)
        self.pct_lo.setSingleStep(0.5)
        self.pct_lo.setSuffix("%")
        ctrl1.addWidget(self.pct_lo)
        ctrl1.addWidget(QLabel("–"))
        self.pct_hi = QDoubleSpinBox()
        self.pct_hi.setRange(50.1, 100)
        self.pct_hi.setValue(99.5)
        self.pct_hi.setSingleStep(0.5)
        self.pct_hi.setSuffix("%")
        ctrl1.addWidget(self.pct_hi)

        btn_redraw = QPushButton("Redraw")
        btn_redraw.clicked.connect(self._redraw)
        ctrl1.addWidget(btn_redraw)
        ctrl1.addStretch()
        root.addLayout(ctrl1)

        # Display controls — row 2: log amplification + save
        ctrl2 = QHBoxLayout()

        self.amp_label = QLabel("Amplification:")
        ctrl2.addWidget(self.amp_label)
        self.amp_edit = QLineEdit("1e10")
        self.amp_edit.setFixedWidth(90)
        self.amp_edit.setPlaceholderText("e.g. 1e10")
        self.amp_edit.setToolTip("Multiplier in: log(1 + image × amplification)")
        ctrl2.addWidget(self.amp_edit)

        self.amp_note = QLabel("→ log(1 + image × amp)")
        self.amp_note.setStyleSheet("color: gray; font-style: italic;")
        ctrl2.addWidget(self.amp_note)

        ctrl2.addStretch()

        self.save_btn = QPushButton("Save stretched image…")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_stretched)
        ctrl2.addWidget(self.save_btn)

        root.addLayout(ctrl2)

        # Show/hide amp controls based on scale selection
        self._set_amp_visible(False)

        # Matplotlib canvas
        self.fig = Figure(figsize=(6, 6), tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        toolbar = NavigationToolbar(self.canvas, self)
        root.addWidget(toolbar)
        root.addWidget(self.canvas, stretch=1)

        self.status_lbl = QLabel("No file loaded.")
        root.addWidget(self.status_lbl)

    def _set_amp_visible(self, visible: bool):
        self.amp_label.setVisible(visible)
        self.amp_edit.setVisible(visible)
        self.amp_note.setVisible(visible)

    def _on_scale_changed(self, text: str):
        self._set_amp_visible(text == "Log")
        self._redraw()

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open FITS file", "", "FITS Files (*.fits *.fit);;All Files (*)"
        )
        if path:
            self.file_edit.setText(path)
            self._load(path)

    def _load(self, path: str):
        try:
            from astropy.io import fits
            with fits.open(path, do_not_scale_image_data=True) as hdul:
                self._data = hdul[0].data.astype(np.float32)
                self._header = hdul[0].header.copy()
        except Exception as exc:
            self.status_lbl.setText(f"Error loading file: {exc}")
            return

        self._source_path = path
        self.save_btn.setEnabled(True)

        h, w = self._data.shape
        bunit = self._header.get("BUNIT", "unknown")
        level = self._header.get("LEVEL", "?")
        self.status_lbl.setText(
            f"{Path(path).name}  |  {w}×{h}  |  Level {level}  |  Units: {bunit}"
        )
        self._redraw()

    def _get_amplification(self) -> float:
        try:
            val = float(self.amp_edit.text())
            if val <= 0:
                raise ValueError
            return val
        except (ValueError, AttributeError):
            self.amp_edit.setText("1e10")
            return 1e10

    def _apply_log_stretch(self, data: np.ndarray) -> np.ndarray:
        """log(1 + image * amplification), clipping negatives before log."""
        amp = self._get_amplification()
        return np.log1p(np.clip(data, 0, None) * amp)

    def _redraw(self):
        if self._data is None:
            return

        data = self._data.copy()
        scale = self.scale_combo.currentText()

        # Apply log stretch first so percentile clip operates on stretched values
        if scale == "Log":
            data = self._apply_log_stretch(data)

        finite = np.isfinite(data)
        if finite.any():
            lo = np.nanpercentile(data[finite], self.pct_lo.value())
            hi = np.nanpercentile(data[finite], self.pct_hi.value())
        else:
            lo, hi = 0.0, 1.0

        display = np.clip(data, lo, hi)
        display[~finite] = lo

        if scale == "Sqrt":
            display = np.sqrt(np.clip(display - lo, 0, None))
        elif scale == "Asinh":
            display = np.arcsinh(np.clip(display - lo, 0, None))

        self.ax.clear()
        self.ax.imshow(display, origin="lower", cmap=self.cmap_combo.currentText(), aspect="equal")
        self.ax.set_xlabel("X (pixels)")
        self.ax.set_ylabel("Y (pixels)")
        self.canvas.draw()

    def _save_stretched(self):
        if self._data is None:
            return

        default_stem = Path(self._source_path).stem if self._source_path else "output"
        default_name = default_stem + "_log_stretched"

        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save stretched image",
            str(Path(self._source_path).parent / default_name) if self._source_path else default_name,
            "FITS 32-bit (*.fits);;TIFF 32-bit (*.tiff)",
        )
        if not path:
            return

        stretched = self._apply_log_stretch(self._data).astype(np.float32)

        try:
            if path.lower().endswith(".fits"):
                self._save_fits(stretched, path)
            else:
                if not path.lower().endswith((".tiff", ".tif")):
                    path += ".tiff"
                self._save_tiff(stretched, path)
            self.status_lbl.setText(f"Saved: {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Save error", str(exc))

    def _save_fits(self, data: np.ndarray, path: str):
        from astropy.io import fits

        header = self._header.copy() if self._header is not None else fits.Header()
        amp = self._get_amplification()
        header["HISTORY"] = f"Log stretch applied: log(1 + image * {amp:.6g})"
        header["BUNIT"] = "log(1 + MSB * amp)"

        hdu = fits.PrimaryHDU(data, header=header)
        hdu.writeto(path, overwrite=True)

    def _save_tiff(self, data: np.ndarray, path: str):
        try:
            import tifffile
            tifffile.imwrite(path, data)
        except ImportError:
            # PIL fallback — mode 'F' is 32-bit float single-channel TIFF
            from PIL import Image
            img = Image.fromarray(data, mode="F")
            img.save(path)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASPIICS Processing Pipeline")
        self.resize(900, 700)

        tabs = QTabWidget()
        tabs.addTab(L2Tab(), "L2 Processing")
        tabs.addTab(L3MergeTab(), "L3 Merge")
        tabs.addTab(FITSViewerTab(), "FITS Viewer")
        self.setCentralWidget(tabs)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
