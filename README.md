# openwebif-vlc-bridge

Play Enigma2 live channels and recordings in VLC on a Windows PC, straight from the
OpenWebif page of the receiver — with seeking, even for recordings stored on a NAS.

```
Browser (OpenWebif page)                       Windows PC                 NAS
┌───────────────────────────┐  GET /vlc?url=  ┌──────────────┐          ┌────────────────────┐
│ Tampermonkey userscript   │ ──────────────▶ │ VLCHelper.py │          │ movie_http.py      │
│ adds "TS" buttons         │  localhost:8124 │ starts VLC   │          │ HTTP + Range (206) │
└───────────────────────────┘                 └──────┬───────┘          └─────────▲──────────┘
                                                     │ VLC plays                  │
             live:       http://<box>:8001/<service ref>  (Enigma2 stream port)   │
             recording:  http://<nas>:8080/<path>.ts  ────────────────────────────┘
```

Why not just use OpenWebif's own links? The `.m3u` playlists OpenWebif hands out need
manual opening, and recordings streamed through the box itself can't be seeked reliably.
Serving the recording directly from the NAS with HTTP Range support lets VLC jump
anywhere in a multi-gigabyte `.ts` file instantly.

## Requirements

- An Enigma2 receiver (any brand) with the **OpenWebif** plugin
- Recordings on a network share that a server can serve over HTTP (here: FreeBSD with Python 3)
- A Windows PC with **VLC** and Python 3.10+
- A browser with **Tampermonkey** (or another userscript manager)
- For use away from home: any VPN or route that lets the PC reach the box and the NAS

The userscript relies on the markup of OpenWebif's web pages (`stream.m3u?ref=` links and
`playRecording(...)` handlers); a different OpenWebif version may need its selectors adjusted.

## Components

| Directory | Runs on | What it does |
|---|---|---|
| [`userscript/`](userscript/) | browser (Tampermonkey) | Adds a **TS** button next to every live channel and every recording on the NAS. Click → the URL goes to VLCHelper; if the helper isn't running, the URL is copied to the clipboard instead. |
| [`vlchelper/`](vlchelper/) | Windows PC | Tiny HTTP server on `localhost:8124`. `GET /vlc?url=<stream>` launches VLC with that URL and brings the VLC window to the foreground. |
| [`nas/`](nas/) | NAS (FreeBSD) | `movie_http.py`: a static file server for the recordings directory with HTTP Range / `206 Partial Content` support (needed for seeking) and `.ts` served as `video/mp2t`; plus an rc.d script to run it as a service. |

## Setup

### 1. NAS (FreeBSD)

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
| `@match` | address of your Enigma2 box's OpenWebif |
| `BOX_STREAM` | the box's stream port, normally `http://<box>:8001/` |
| `NAS_ROOT` | where `movie_http.py` serves the recordings directory |
| `BOX_MOUNT` | the same directory as the box sees it (prefix of the recording paths in OpenWebif) |
| `VLC_HELPER` | VLCHelper's address, normally unchanged |

Recordings whose path does not start with `BOX_MOUNT` (e.g. on the box's internal disk)
get no button.

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
