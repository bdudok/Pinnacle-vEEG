# Pinnacle-vEEG
Video-EEG recording on the Pinnacle setups, LNCM / Dudok lab.

Split from the [Recorder](https://github.com/bdudok/Recorder) repo on 2026-10-25 with its history.
Recorder keeps the apps for the Bruker 2P setup.

## Contents

- `VideoEEG/`: video-EEG recorder. Continuous hourly video files and random-interval TTL pulses for
  aligning the video to the EEG. Usage, settings, output files: [VideoEEG/README.md](VideoEEG/README.md).
- `Camera/nncam.py`, `Camera/nncam.dll`: camera SDK, used by VideoEEG.
- `Camera/EEG-Cam.py`: the old recorder, replaced by VideoEEG. Kept for reference; it needs PyQt5,
  pyqtgraph and opencv, which the `veeg` environment does not have.
- `OptoTrigger/ClosedLoop_Pinnacle/`: Arduino sketch for the closed-loop optogenetics accessory board.
  Upload it with the Arduino IDE (needs the elapsedMillis library).

## Setup on a recording PC

1. Install Git and Miniforge (or Anaconda).
2. Clone the repo, e.g. into `%USERPROFILE%\PycharmProjects`:
   `git clone https://github.com/bdudok/Pinnacle-vEEG.git`
3. From the repo folder: `conda env create -f VideoEEG/environment.yml`
4. Check the camera, make the desktop shortcuts and set up Windows for 24/7 recording as described in
   [VideoEEG/README.md](VideoEEG/README.md), "Install (recording PC)".

## Moving an existing PC from the Recorder repo

The Pinnacle PCs set up before the split run `vEEG.bat` from their Recorder checkout. They keep working as
they are, but don't pull Recorder on them: VideoEEG is removed from Recorder after the split. When a PC
needs an update:

1. Stop the recordings and close the vEEG windows.
2. Clone this repo (step 2 above). The `veeg` conda environment stays as it is; update it with
   `conda env update -f VideoEEG/environment.yml` if `environment.yml` changed.
3. Point each desktop shortcut's Target at `Pinnacle-vEEG\VideoEEG\vEEG.bat` (keep the ` --cam N` at the
   end). Settings and logs stay in `%USERPROFILE%\.veeg_recorder\`, so each window keeps its camera.
4. Start the windows and check each preview shows the right camera.
