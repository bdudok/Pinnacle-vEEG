"""Single-camera video recorder for post-surgery monitoring.

    python -m MonitorCam.gui            # USB (DirectShow) camera
    python -m MonitorCam.gui --fake     # ffmpeg test pattern instead of a camera

One ffmpeg process opens the camera and sends a small preview to this window. While recording, the
same process also encodes H.264 into one MKV file per recording, named <name>-<start time>.mkv.
The start time is also stored in the file's metadata (creation_time in UTC, START_TIME_LOCAL with the UTC offset).
"""
import argparse
import dataclasses
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

APP_DIR = Path.home() / '.monitorcam'
SETTINGS_PATH = APP_DIR / 'settings.json'
LOG_PATH = APP_DIR / 'ffmpeg.log'
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
PREVIEW_W = 640
RESTART_S = 5  # wait before restarting ffmpeg after it exits unexpectedly


@dataclasses.dataclass
class Settings:
    device: str = ''            # DirectShow camera name; empty: the first camera found
    out_dir: str = str(Path('C:/MonitorCam') if os.name == 'nt' else Path.home() / 'MonitorCam')
    prefix: str = 'mouse'
    width: int = 1920
    height: int = 1080
    framerate: int = 30
    encoder: str = 'auto'       # 'auto', 'h264_nvenc', 'h264_qsv' or 'libx264'
    quality: int = 23           # CRF / CQ / global_quality; lower is better quality and larger files
    preview_fps: int = 10
    ffmpeg: str = 'ffmpeg'
    min_free_gb: float = 20.0   # status shows a warning below this

    @classmethod
    def load(cls):
        if not SETTINGS_PATH.exists():
            return cls()
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def save(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(dataclasses.asdict(self), f, indent=2)

    @property
    def preview_size(self):
        return PREVIEW_W, round(PREVIEW_W * self.height / self.width / 2) * 2


def list_devices(ffmpeg):
    """DirectShow video device names."""
    try:
        out = subprocess.run([ffmpeg, '-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
                             check=False, capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stderr
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_devices(out)


def parse_devices(text):
    return re.findall(r'\]\s+"([^"]+)"\s+\(video\)', text)


def encoder_args(encoder, quality):
    if encoder == 'h264_nvenc':
        return ['-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'vbr', '-cq', str(quality), '-b:v', '0']
    if encoder == 'h264_qsv':
        return ['-c:v', 'h264_qsv', '-preset', 'medium', '-global_quality', str(quality)]
    if encoder == 'libx264':
        return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', str(quality)]
    raise ValueError(f'unknown encoder {encoder}')


def choose_encoder(s):
    """The configured encoder, or for 'auto' the first GPU encoder that passes a test encode, else libx264."""
    if s.encoder != 'auto':
        return s.encoder
    for encoder in ('h264_nvenc', 'h264_qsv'):
        cmd = [s.ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
               '-i', f'testsrc2=s={s.width}x{s.height}:r={s.framerate}', '-frames:v', '10',
               *encoder_args(encoder, s.quality), '-pix_fmt', 'yuv420p', '-f', 'null', '-']
        try:
            result = subprocess.run(cmd, check=False, capture_output=True, timeout=30, creationflags=NO_WINDOW)
            if result.returncode == 0:
                return encoder
        except (OSError, subprocess.TimeoutExpired):
            pass
    return 'libx264'


def recording_path(s, start):
    return Path(s.out_dir) / f'{s.prefix}-{start.strftime("%Y-%m-%dT%H-%M-%S")}.mkv'


def ffmpeg_command(s, device, encoder=None, start=None, fake=False):
    """Capture from the camera, write the preview to stdout, and record if `encoder` is given.
    `start`: timezone-aware time when recording starts, for the file name and metadata."""
    if fake:
        source = ['-re', '-f', 'lavfi', '-i', f'testsrc2=s={s.width}x{s.height}:r={s.framerate}']
    else:
        source = ['-f', 'dshow', '-rtbufsize', '512M', '-vcodec', 'mjpeg', '-video_size', f'{s.width}x{s.height}',
                  '-framerate', str(s.framerate), '-i', f'video={device}']
    cmd = [s.ffmpeg, '-hide_banner', '-nostats', '-loglevel', 'warning', '-y', *source]
    if encoder:
        utc = start.astimezone(datetime.UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        cmd += ['-map', '0:v', *encoder_args(encoder, s.quality), '-pix_fmt', 'yuv420p', '-g', str(2 * s.framerate),
                '-metadata', f'creation_time={utc}',
                '-metadata', f'START_TIME_LOCAL={start.isoformat(timespec="milliseconds")}',
                '-metadata', f'CAMERA={device}',
                '-f', 'matroska', str(recording_path(s, start))]
    w, h = s.preview_size
    cmd += ['-map', '0:v', '-vf', f'fps={s.preview_fps},scale={w}:{h}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    return cmd


class Capture:
    """Runs one ffmpeg process; keeps the latest preview frame and the last ffmpeg messages."""

    def __init__(self, cmd, size):
        self.size = size
        self.frame = None
        self.messages = deque(maxlen=6)
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=NO_WINDOW)
        threading.Thread(target=self._read_frames, daemon=True).start()
        threading.Thread(target=self._read_log, daemon=True).start()

    def _read_frames(self):
        # Read continuously: a full pipe would stall ffmpeg and drop camera frames.
        n = self.size[0] * self.size[1] * 3
        while True:
            data = self.proc.stdout.read(n)
            if len(data) < n:
                return
            self.frame = data

    def _read_log(self):
        with open(LOG_PATH, 'a', encoding='utf-8') as log:
            for line in self.proc.stderr:
                line = line.decode(errors='replace').rstrip()
                if line:
                    stamped = f'{time.strftime("%Y-%m-%d %H:%M:%S")} {line}'
                    self.messages.append(stamped)
                    log.write(stamped + '\n')
                    log.flush()

    def running(self):
        return self.proc.poll() is None

    def stop(self):
        """Ask ffmpeg to finish the file, kill it if it does not exit."""
        if self.running():
            try:
                self.proc.stdin.write(b'q')
                self.proc.stdin.flush()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def free_gb(path):
    path = Path(path)
    while not path.exists() and path != path.parent:
        path = path.parent
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return None


def keep_awake():
    if os.name == 'nt':
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, fake=False):
        super().__init__()
        self.fake = fake
        self.s = Settings.load()
        self.capture = None
        self.encoder = None      # set while recording
        self.rec_start = None
        self.died_at = None
        self.file = None
        self.messages = deque(maxlen=6)
        self.setWindowTitle('MonitorCam')
        self.resize(1000, 750)

        self.device = QtWidgets.QComboBox()
        self.device.setMinimumWidth(250)
        devices = ['test pattern'] if fake else list_devices(self.s.ffmpeg)
        self.device.addItems(devices)
        if self.s.device in devices:
            self.device.setCurrentText(self.s.device)
        self.device.currentTextChanged.connect(self.restart_preview)
        self.folder_button = QtWidgets.QPushButton('Select folder')
        self.folder_button.clicked.connect(self.choose_folder)
        self.folder_label = QtWidgets.QLabel(self.s.out_dir)
        self.prefix = QtWidgets.QLineEdit(self.s.prefix)
        self.prefix.setPlaceholderText('file name')
        self.rec_button = QtWidgets.QPushButton('Record')
        self.rec_button.setMinimumWidth(140)
        self.rec_button.clicked.connect(self.toggle_recording)

        self.state_label = QtWidgets.QLabel()
        font = self.state_label.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self.state_label.setFont(font)
        self.details_label = QtWidgets.QLabel()
        self.video = QtWidgets.QLabel()
        self.video.setAlignment(QtCore.Qt.AlignCenter)
        self.video.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.video.setStyleSheet('background-color: black')
        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(90)

        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel('Camera:'))
        row1.addWidget(self.device)
        row1.addStretch(1)
        row1.addWidget(self.rec_button)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(self.folder_button)
        row2.addWidget(self.folder_label, stretch=1)
        row2.addWidget(QtWidgets.QLabel('Name:'))
        row2.addWidget(self.prefix)
        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self.state_label)
        layout.addWidget(self.details_label)
        layout.addWidget(self.video, stretch=1)
        layout.addWidget(self.log_box)
        central = QtWidgets.QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        if not devices:
            self.note('No camera found. Connect the camera and restart the app.')
        self.restart_preview()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000 // self.s.preview_fps)

    def note(self, text):
        self.messages.append(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {text}')

    # --- ffmpeg ---
    def start_capture(self):
        device = self.device.currentText()
        if not device:
            return
        start = None
        if self.encoder:
            # After a camera restart this starts a new file.
            start = datetime.datetime.now().astimezone()
            self.file = recording_path(self.s, start)
            self.note(f'recording to {self.file}')
        self.capture = Capture(ffmpeg_command(self.s, device, self.encoder, start, self.fake), self.s.preview_size)
        self.died_at = None

    def stop_capture(self):
        if self.capture is not None:
            self.messages.extend(self.capture.messages)
            self.capture.stop()
            self.capture = None

    def restart_preview(self):
        self.stop_capture()
        self.start_capture()

    # --- controls ---
    def choose_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select folder', self.folder_label.text())
        if folder:
            self.folder_label.setText(folder)

    def toggle_recording(self):
        if self.encoder:
            if QtWidgets.QMessageBox.question(self, 'Stop recording', 'Stop the recording?') != \
                    QtWidgets.QMessageBox.Yes:
                return
            self.encoder = None
            self.rec_start = None
            self.note('recording stopped')
        else:
            self.s.device = self.device.currentText()
            self.s.out_dir = self.folder_label.text()
            self.s.prefix = re.sub(r'[^\w\-.]', '_', self.prefix.text().strip()) or 'mouse'
            self.prefix.setText(self.s.prefix)
            self.s.save()
            try:
                Path(self.s.out_dir).mkdir(parents=True, exist_ok=True)
            except OSError as ex:
                QtWidgets.QMessageBox.warning(self, 'Record', f'Cannot use folder {self.s.out_dir}:\n{ex}')
                return
            self.encoder = choose_encoder(self.s)
            self.rec_start = time.time()
            keep_awake()
            self.note(f'recording started, encoder {self.encoder}')
        self.restart_preview()
        self.update_controls()

    # --- display ---
    def tick(self):
        cap = self.capture
        if cap is not None and not cap.running():
            self.messages.extend(cap.messages)
            self.capture = None
            self.died_at = time.time()
            self.note(f'ffmpeg stopped, restarting in {RESTART_S} s')
        if self.capture is None and self.died_at and time.time() - self.died_at > RESTART_S:
            self.start_capture()
        if self.capture is not None and self.capture.frame is not None:
            w, h = self.s.preview_size
            image = QtGui.QImage(self.capture.frame, w, h, 3 * w, QtGui.QImage.Format_RGB888)
            self.video.setPixmap(QtGui.QPixmap.fromImage(image).scaled(
                self.video.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        self.update_controls()

    def update_controls(self):
        recording = self.encoder is not None
        for w in (self.device, self.folder_button, self.prefix):
            w.setEnabled(not recording)
        self.rec_button.setEnabled(recording or bool(self.device.currentText()))
        self.rec_button.setText('Stop' if recording else 'Record')
        self.rec_button.setStyleSheet('background-color: #c62828; color: white' if recording else '')
        ok = self.capture is not None and self.capture.frame is not None
        if self.capture is None or not self.capture.running():
            self.set_state('CAMERA NOT RUNNING' + (' (recording resumes when it restarts)' if recording else ''),
                           '#c62828')
        elif recording:
            elapsed = int(time.time() - self.rec_start)
            self.set_state(f'RECORDING {elapsed // 3600:d}:{elapsed // 60 % 60:02d}:{elapsed % 60:02d}', '#2e7d32')
        else:
            self.set_state('Preview (not recording)' if ok else 'Starting camera...', '#555555')
        free = free_gb(self.folder_label.text())
        disk = f'disk free: {free:.0f} GB' if free is not None else 'disk free: ?'
        if free is not None and free < self.s.min_free_gb:
            disk = f'<span style="color:#c62828"><b>{disk} (LOW)</b></span>'
        file = f' | file: {self.file}' if recording else ''
        self.details_label.setText(f'{self.s.width}x{self.s.height} {self.s.framerate} fps | {disk}{file}')
        lines = list(self.messages) + (list(self.capture.messages) if self.capture else [])
        text = '\n'.join(lines[-6:])
        if self.log_box.toPlainText() != text:
            self.log_box.setPlainText(text)

    def set_state(self, text, color):
        self.state_label.setText(text)
        self.state_label.setStyleSheet(f'color: {color}')

    def closeEvent(self, event):
        if self.encoder and QtWidgets.QMessageBox.question(
                self, 'Close', 'This stops the recording. Close the window?') != QtWidgets.QMessageBox.Yes:
            event.ignore()
            return
        self.timer.stop()
        self.encoder = None
        self.stop_capture()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fake', action='store_true', help='use an ffmpeg test pattern instead of a camera')
    args = parser.parse_args()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow(args.fake)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
