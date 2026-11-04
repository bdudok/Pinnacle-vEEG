# MonitorCam

Records one USB camera to video files, for monitoring a mouse after surgery and reviewing the video for
status epilepticus. No triggering or TTL. Used with the ELP-USB4KCAM01H-CFV.

## Install

1. Set up the PC, the repo and the environment as in the [repo README](../README.md).
2. Right-click `MonitorCam\MonitorCam.bat` → Show more options → Send to → Desktop (create shortcut).
3. Set the Windows power plan to never sleep, and pause Windows Update during recordings. An update restart ends
   the recording.

## Use

1. Double-click the desktop shortcut. The window shows the camera preview.
2. If more than one camera is listed, choose the camera.
3. Press **Select folder** and type a **Name** (e.g. the mouse ID).
4. Press **Record**. The status line shows RECORDING and the elapsed time.
5. To stop, press **Stop**. Closing the window also stops the recording.

Each recording is one file, `<Name>-<start date and time>.mkv`, in the selected folder. Video is H.264, 1920x1080,
30 fps, about 1-3 GB per hour.

The start time is also stored inside the file, to within about 2 s: `creation_time` (UTC) and `START_TIME_LOCAL`
(local time with UTC offset, e.g. `2026-11-04T14:03:22.512-06:00`). To read it, open the file in MediaInfo, or run
`ffprobe <file>`. The recording's end time is the start time plus the video duration.

If the camera stops (unplugged, USB error), the window shows CAMERA NOT RUNNING and retries every 5 s. Recording
continues in a new file when the camera returns.

## Settings and logs

Folder `%USERPROFILE%\.monitorcam\`:
- `settings.json`: also holds settings not shown in the window: `width`, `height`, `framerate`, `encoder` (`auto`
  uses a GPU encoder if one works, otherwise `libx264` on the CPU), `quality` (lower is better and larger),
  `min_free_gb`. Edit it with the app closed.
- `ffmpeg.log`: ffmpeg messages. Messages like `real-time buffer too full` mean frames were dropped: the PC is
  too slow for the encoder. Lower `width`/`height` (e.g. 1280x720) or set `encoder` to a GPU encoder.

To list the camera's resolutions and frame rates, in a Command Prompt:
`ffmpeg -list_options true -f dshow -i video="<camera name as shown in the window>"`.
Use a size listed for `vcodec=mjpeg`.

`uv run python -m MonitorCam.gui --fake` runs the app with a test pattern instead of a camera.
