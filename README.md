# openwebif-vlc-bridge

Play Enigma2 live channels and recordings in VLC on a Windows PC with one click, straight
from the OpenWebif page of the receiver — with seeking.

```
Browser (OpenWebif page)                       Windows PC
┌───────────────────────────┐  GET /vlc?url=  ┌──────────────┐
│ Tampermonkey userscript   │ ──────────────▶ │ VLCHelper.py │ ──▶ VLC plays one of:
│ adds "TS" buttons         │  localhost:8124 │ starts VLC   │
└───────────────────────────┘                 └──────────────┘

  live channel:          http://<box>:8001/<service ref>             (Enigma2 stream port)
  recording, "box" mode: http://<box>/file?file=/media/.../<name>.ts (OpenWebif itself)
  recording, "nas" mode: http://<nas>:8080/<path>/<name>.ts          (optional movie_http.py)
```

Why? Depending on the version, OpenWebif's own play buttons either hand out `.m3u`
playlists to be opened by hand, or start a built-in browser player — which on our setup
did not play recordings at all. The **TS** buttons skip the browser-side playback entirely
and open the stream in VLC directly. Both recording sources support HTTP Range requests,
so VLC can jump anywhere in a multi-gigabyte `.ts` file.

**Which recording source?** `"box"` (default) needs nothing beyond the userscript and
VLCHelper, and covers recordings on the box's own disk too. If the recordings are on a NAS,
`"nas"` serves them straight from there: in one measurement on a gigabit LAN, 112 MB/s
directly from the NAS versus 39 MB/s (wired box) and 10 MB/s (box behind a Wi-Fi extender)
through the box. An HD recording needs only about 3 MB/s, so `"box"` is usually fine; `"nas"`
mainly helps when the box has a slow link or is busy recording.

## Requirements

- An Enigma2 receiver (any brand) with the **OpenWebif** plugin
- A Windows PC with **VLC** and Python 3.10+
- A browser with **Tampermonkey** (or another userscript manager)
- Optional, for `"nas"` mode: recordings on a NAS share, and Python 3 on the NAS
  (the included rc.d script is for FreeBSD)
- For use away from home: any VPN or route that lets the PC reach the box (and the NAS)

The userscript relies on the markup of OpenWebif's web pages (`stream.m3u?ref=` links and
`playRecording(...)` handlers); a different OpenWebif version may need its selectors adjusted.

## Components

| Directory | Runs on | What it does |
|---|---|---|
| [`userscript/`](userscript/) | browser (Tampermonkey) | Adds a **TS** button next to every live channel and recording. Click → the URL goes to VLCHelper; if the helper isn't running, the URL is copied to the clipboard instead. |
| [`vlchelper/`](vlchelper/) | Windows PC | Tiny HTTP server on `localhost:8124`. `GET /vlc?url=<stream>` launches VLC with that URL and brings the VLC window to the foreground. |
| [`nas/`](nas/) | NAS (FreeBSD) — optional | Only for `"nas"` mode. `movie_http.py`: a static file server for the recordings directory with HTTP Range / `206 Partial Content` support (needed for seeking) and `.ts` served as `video/mp2t`; plus an rc.d script to run it as a service. |

## Setup

### 1. NAS (FreeBSD) — only for `"nas"` mode

Skip this step with the default `RECORDING_SOURCE = "box"`.

The box must record onto a share of the NAS (e.g. CIFS/NFS mounted on the box as
`/media/net/NAS/`). On the NAS, the same directory is served over HTTP:

```sh
install -m 755 nas/movie_http.py /usr/local/libexec/movie_http.py
install -m 555 nas/rc.d/movie_http /usr/local/etc/rc.d/movie_http
sysrc movie_http_enable=YES
sysrc movie_http_dir=/mnt/movie      # optional, these are the defaults
sysrc movie_http_port=8080
service movie_http start
```

Needs only `python3` (standard library). The service runs under daemon(8) as user
`nobody` (`movie_http_user`) and is restarted if it dies. Check:
`fetch -o - http://<nas>:8080/` lists the files.

Don't add `-u` to the daemon(8) arguments: rc.subr already switches to `movie_http_user`.

> The server has no authentication — keep it on your LAN / VPN only.

### 2. VLCHelper (Windows)

Requires Python 3.10+ and [VLC](https://www.videolan.org/). Adjust `VLC_EXE` at the top of
`VLCHelper.py` if VLC is installed elsewhere, then start it without a console window:

```bat
pythonw.exe VLCHelper.py
```

To start it at login, put a shortcut to that command in `shell:startup`. Under `pythonw`
the output goes to `VLCHelper.log` next to the script.

Only `http`, `https`, `rtsp` and `udp` URLs are accepted: any web page can make your
browser call `localhost`, so the helper refuses anything else.

### 3. Userscript

1. Install [Tampermonkey](https://www.tampermonkey.net/).
2. Create a new script and paste [`userscript/openwebif-ts-buttons.user.js`](userscript/openwebif-ts-buttons.user.js).
3. Edit the configuration block at the top:

| Setting | Meaning |
|---|---|
| `@match` | address of your Enigma2 box's OpenWebif (add one `@match` line per box) |
| `BOX_STREAM` | the box's stream port, normally `http://<box>:8001/` |
| `VLC_HELPER` | VLCHelper's address, normally unchanged |
| `RECORDING_SOURCE` | `"box"` (default) or `"nas"`, see above |
| `NAS_ROOT` | `"nas"` only: where `movie_http.py` serves the recordings directory |
| `BOX_MOUNT` | `"nas"` only: the same directory as the box sees it (prefix of the recording paths in OpenWebif) |

In `"box"` mode the recording is fetched from the box whose OpenWebif page you clicked on.
In `"nas"` mode, recordings whose path does not start with `BOX_MOUNT` (e.g. on the box's
internal disk) get no button.

If OpenWebif has authentication enabled, VLC will ask for the credentials when it opens
a `"box"` recording.

## Notes

- **File names:** recordings with non-ASCII names may exist on the NAS in both Unicode NFC
  and NFD form. The userscript encodes the path exactly as OpenWebif reports it, without
  normalizing, so both forms work.
- **VLC settings:** with *Allow only one instance* and *Enqueue items* enabled, new streams
  are added to the playlist of the already running VLC; VLCHelper still raises its window.
- **Remote use:** nothing here is VPN-specific; the PC just has to reach the box and the NAS.
  Seeking works well remotely too, since VLC only fetches the byte ranges it plays.

## License

[MIT](LICENSE)
