// ==UserScript==
// @name         OpenWebif TS Buttons (LIVE, clipboard)
// @version      0.3
// @description  Adds TS buttons to OpenWebif: live channels and NAS recordings open in VLC via VLCHelper
// @license      MIT
// @match        *://192.168.1.97/*
// @grant        GM_setClipboard
// ==/UserScript==

(function() {
    'use strict';

    // ---- Configuration: change these to match your network (and the @match line above) ----
    const BOX_STREAM = "http://192.168.1.97:8001/";          // Enigma2 live stream port
    const NAS_ROOT   = "http://192.168.1.4:8080/";           // movie_http.py on the NAS, serving its movie dir
    const BOX_MOUNT  = "/media/net/NAS/";                    // the same directory as mounted on the box
    const VLC_HELPER = "http://localhost:8124/vlc?url=";     // VLCHelper.py

    // Encode each path segment exactly as given. No Unicode normalization: names on the NAS
    // are a mix of NFC and NFD, and OpenWebif reports the exact on-disk form.
    function encodePath(path) {
        return path.split("/").map(encodeURIComponent).join("/");
    }

    // Open in VLC via the local helper; if the helper is not running, copy the URL instead.
    // mode "no-cors": the helper sends no CORS headers, so a normal fetch would reject even
    // on success. An opaque no-cors fetch rejects only when the connection itself fails.
    function openInVLC(url) {
        fetch(VLC_HELPER + encodeURIComponent(url), { mode: "no-cors" })
            .catch(function() {
                GM_setClipboard(url);
                alert("VLCHelper ei vastaa – TS-URL kopioitu leikepöydälle:\n\n" + url +
                      "\n\nAvaa VLC → Media → Open Network Stream → Ctrl+V");
            });
    }

    function addButton(el, url) {
        const tsButton = document.createElement("a");
        tsButton.href = "#";
        tsButton.textContent = "TS";
        tsButton.title = url;
        tsButton.style.marginLeft = "10px";
        tsButton.style.color = "#0af";
        tsButton.style.fontWeight = "bold";
        tsButton.addEventListener("click", function(e) {
            e.preventDefault();
            openInVLC(url);
        });
        el.dataset.tsAdded = "1";
        el.parentNode.insertBefore(tsButton, el.nextSibling);
    }

    function addTSButtons() {

        // LIVE: <a href="web/stream.m3u?ref=1:0:19:...:&name=...">
        document.querySelectorAll('a[href*="stream.m3u?ref="]').forEach(function(el) {
            if (el.dataset.tsAdded === "1") return;
            const serviceRef = new URL(el.href, location.href).searchParams.get("ref");
            if (!serviceRef) return;
            addButton(el, BOX_STREAM + serviceRef);
        });

        // RECORDINGS: onclick="playRecording('1%3A0%3A...%3A/media/net/NAS/<dir>/.../<file>')"
        document.querySelectorAll('a[onclick*="playRecording"]').forEach(function(el) {
            if (el.dataset.tsAdded === "1") return;
            const fileMatch = el.getAttribute("onclick").match(/playRecording\('([^']+)'/);
            if (!fileMatch) return;

            // "<service ref>:/media/net/NAS/leffat/x.ts" -> NAS_ROOT + "leffat/x.ts"
            const fullPath = decodeURIComponent(fileMatch[1]);
            const at = fullPath.indexOf(BOX_MOUNT);
            if (at < 0) return;   // not on the NAS (e.g. local HDD of the PVR)
            addButton(el, NAS_ROOT + encodePath(fullPath.slice(at + BOX_MOUNT.length)));
        });
    }

    addTSButtons();
    setInterval(addTSButtons, 500);

})();
