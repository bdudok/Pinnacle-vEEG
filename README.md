# Pinnacle-vEEG
Video-EEG recording on the Pinnacle setups, LNCM / Dudok lab.

Split from the [Recorder](https://github.com/bdudok/Recorder) repo on 2026-10-25 with its history.
Recorder keeps the apps for the Bruker 2P setup.

## Contents

- `VideoEEG/`: video-EEG recorder. Continuous hourly video files and random-interval TTL pulses for
  aligning the video to the EEG. Usage, settings, output files: [VideoEEG/README.md](VideoEEG/README.md).
- `MonitorCam/`: single USB camera recorder for post-surgery monitoring, no TTL. Usage:
  [MonitorCam/README.md](MonitorCam/README.md).
- `Camera/nncam.py`, `Camera/nncam.dll`: camera SDK, used by VideoEEG.
- `Camera/EEG-Cam.py`: the old recorder, replaced by VideoEEG. Kept for reference; it needs PyQt5,
  pyqtgraph and opencv, which the repo environment does not have.
- `OptoTrigger/ClosedLoop_Pinnacle/`: Arduino sketch for the closed-loop optogenetics accessory board.
  Upload it with the Arduino IDE (needs the elapsedMillis library).

## Setup on a recording PC

The Python environment is made with [uv](https://docs.astral.sh/uv/) from `pyproject.toml` and `uv.lock`, in
the repo's `.venv` folder. ffmpeg is installed separately with winget.

1. Install Git for Windows.
2. In a Command Prompt:
   ```
   winget install astral-sh.uv
   winget install Gyan.FFmpeg
   ```
3. Close the Command Prompt and open a new one, so that `uv` and `ffmpeg` are on PATH. Then:
   ```
   mkdir %USERPROFILE%\PycharmProjects
   cd %USERPROFILE%\PycharmProjects
   git clone https://github.com/bdudok/Pinnacle-vEEG.git
   cd Pinnacle-vEEG
   uv sync --locked
   ```
   uv downloads Python 3.11 if needed.
4. Continue with the app's README: [VideoEEG](VideoEEG/README.md), "Install (recording PC)", or
   [MonitorCam](MonitorCam/README.md), "Install".

After a `git pull` that changes `uv.lock`, run `uv sync --locked` again in the repo folder.

## Moving an existing PC from conda

The Pinnacle PCs set up before 2026-11 run `vEEG.bat` with the `veeg` conda environment, some from a Recorder
checkout. They keep working as they are. Don't pull on them until they need an update; the current `vEEG.bat`
needs the uv environment. To update a PC:

1. Stop the recordings and close the vEEG windows.
2. Do steps 2-3 of the setup above. If the PC already has a Pinnacle-vEEG checkout, run `git pull` in it
   instead of cloning.
3. Point each desktop shortcut's Target at `Pinnacle-vEEG\VideoEEG\vEEG.bat` (keep the ` --cam N` at the
   end). Settings and logs stay in `%USERPROFILE%\.veeg_recorder\`, so each window keeps its camera.
4. Start the windows. Check that each preview shows the right camera and that the status line shows
   `encoder: h264_nvenc`.
5. Miniforge or Anaconda can then be uninstalled, if nothing else on the PC uses it.
