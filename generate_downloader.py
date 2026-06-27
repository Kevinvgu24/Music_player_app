import json
from pathlib import Path

# Load track list
tracks_json_path = Path(__file__).parent / "tracks_list.json"
with open(tracks_json_path, "r", encoding="utf-8") as f:
    tracks = json.load(f)

# HTML template
html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>YouTube Cover Art Downloader</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #070b13;
            --card-bg: rgba(13, 19, 32, 0.6);
            --accent-color: #1d90f4;
            --text-color: #ffffff;
            --text-muted: #a0aab8;
            --success-color: #10b981;
            --error-color: #ef4444;
        }

        body {
            margin: 0;
            padding: 24px;
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            background-image: radial-gradient(circle at top right, rgba(29, 144, 244, 0.1), transparent 400px);
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        h1 {
            font-weight: 800;
            font-size: 36px;
            margin: 0 0 8px 0;
            background: linear-gradient(135deg, #1d90f4, #00ffcc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .subtitle {
            color: var(--text-muted);
            margin-bottom: 24px;
            font-size: 16px;
        }

        .dashboard {
            display: grid;
            grid-template-columns: 1.5fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }

        .card {
            background: var(--card-bg);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(12px);
        }

        .progress-bar-container {
            height: 14px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 7px;
            overflow: hidden;
            margin: 16px 0;
        }

        .progress-bar {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #1d90f4, #00ffcc);
            transition: width 0.3s ease;
        }

        .stats {
            display: flex;
            justify-content: space-between;
            font-size: 14px;
            color: var(--text-muted);
        }

        .terminal {
            font-family: 'JetBrains Mono', monospace;
            background: #05080f;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 16px;
            height: 160px;
            overflow-y: auto;
            font-size: 12px;
            color: #b3c0d1;
        }

        .terminal-line {
            margin-bottom: 6px;
        }

        .terminal-success { color: var(--success-color); }
        .terminal-error { color: var(--error-color); }
        .terminal-info { color: var(--accent-color); }

        .btn {
            background: var(--accent-color);
            color: white;
            border: none;
            padding: 12px 28px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 14px;
        }

        .btn:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }

        .btn:disabled {
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-muted);
            cursor: not-allowed;
            transform: none;
        }

        .grid-container {
            margin-top: 24px;
        }

        .grid-title {
            font-weight: 600;
            font-size: 18px;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
            gap: 16px;
            max-height: 480px;
            overflow-y: auto;
            padding: 12px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            background: rgba(0, 0, 0, 0.2);
        }

        .song-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 10px;
            padding: 8px;
            text-align: center;
            font-size: 11px;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 140px;
        }

        .song-card.pending { border-color: rgba(255, 255, 255, 0.08); }
        .song-card.fetching { border-color: var(--accent-color); background: rgba(29, 144, 244, 0.08); box-shadow: 0 0 10px rgba(29, 144, 244, 0.15); }
        .song-card.success { border-color: var(--success-color); background: rgba(16, 185, 129, 0.08); }
        .song-card.error { border-color: var(--error-color); background: rgba(239, 68, 68, 0.08); }

        .song-thumb-wrapper {
            width: 100%;
            height: 75px;
            border-radius: 6px;
            overflow: hidden;
            position: relative;
            background: #111;
            margin-bottom: 8px;
        }

        .song-thumb {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .song-status-badge {
            position: absolute;
            bottom: 4px;
            right: 4px;
            font-size: 9px;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: bold;
        }

        .song-card.pending .song-status-badge { background: #333; color: #aaa; }
        .song-card.fetching .song-status-badge { background: var(--accent-color); color: #fff; }
        .song-card.success .song-status-badge { background: var(--success-color); color: #fff; }
        .song-card.error .song-status-badge { background: var(--error-color); color: #fff; }

        .song-info {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .song-title {
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            color: #fff;
        }

        .song-artist {
            color: var(--text-muted);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
</head>
<body>
    <div class="container">
        <h1>YouTube Cover Art Downloader</h1>
        <div class="subtitle">Fetching and packing cover arts from YouTube Music for offline playlist.</div>

        <div class="dashboard">
            <div class="card">
                <h2>Progress Control</h2>
                <div class="progress-bar-container">
                    <div class="progress-bar" id="progressBar"></div>
                </div>
                <div class="stats">
                    <span id="progressText">Completed: 0/0 (0%)</span>
                    <span id="statusText">Idle</span>
                </div>
                <div style="margin-top: 24px; display: flex; gap: 12px;">
                    <button class="btn" id="startBtn" onclick="startDownload()">Start Fetching</button>
                    <button class="btn" id="downloadBtn" onclick="saveZip()" disabled style="background: var(--success-color);">Download ZIP</button>
                </div>
            </div>

            <div class="card" style="display: flex; flex-direction: column;">
                <h2>System Logs</h2>
                <div class="terminal" id="terminal">
                    <div class="terminal-line terminal-info">System initialized. Ready to fetch.</div>
                </div>
            </div>
        </div>

        <div class="card grid-container">
            <div class="grid-title">
                <span>Songs Queue</span>
                <span id="queueStats" style="font-size: 13px; color: var(--text-muted); font-weight: normal;">Total: 0</span>
            </div>
            <div class="grid" id="songGrid"></div>
        </div>
    </div>

    <script>
        const tracks = ###TRACKS_JSON###;

        let instances = [
            "yewtu.be",
            "invidious.lunar.icu",
            "iv.melmac.space",
            "invidious.projectsegfau.lt",
            "invidious.flokinet.to",
            "invidious.privacydev.net",
            "inv.tux.im"
        ];
        
        const zip = new JSZip();
        let activeDownloads = 0;
        let completedCount = 0;
        let successCount = 0;
        let errorCount = 0;
        let isRunning = false;
        let queue = [];

        function log(message, type = "info") {
            const term = document.getElementById("terminal");
            const line = document.createElement("div");
            line.className = `terminal-line terminal-${type}`;
            const time = new Date().toLocaleTimeString();
            line.textContent = `[${time}] ${message}`;
            term.appendChild(line);
            term.scrollTop = term.scrollHeight;
        }

        // SHA-1 helper matching Python's hashlib.sha1
        async function sha1(str) {
            const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(str));
            return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
        }

        async function loadInstances() {
            try {
                log("Fetching active Invidious instances list...", "info");
                let res = await fetch("https://api.invidious.io/instances.json?sort_by=type,health");
                let data = await res.json();
                let fetched = data.filter(item => item[1] && item[1].type === "https" && item[1].health > 80 && item[1].api)
                                  .map(item => item[0]);
                if (fetched.length > 0) {
                    // Prepend standard stable ones just in case
                    instances = [...new Set([...fetched, ...instances])];
                    log(`Loaded ${instances.length} healthy Invidious instances.`, "success");
                }
            } catch (e) {
                log("Failed to fetch fresh instances, using built-in fallbacks.", "info");
            }
        }

        function buildQueueUI() {
            const grid = document.getElementById("songGrid");
            grid.innerHTML = "";
            document.getElementById("queueStats").textContent = `Total: ${tracks.length}`;
            
            tracks.forEach((t, index) => {
                const card = document.createElement("div");
                card.className = "song-card pending";
                card.id = `card-${index}`;
                
                card.innerHTML = `
                    <div class="song-thumb-wrapper">
                        <div class="song-thumb" id="thumb-${index}" style="background-color: #111;"></div>
                        <span class="song-status-badge" id="badge-${index}">Waiting</span>
                    </div>
                    <div class="song-info">
                        <div class="song-title" title="${t.title}">${t.title}</div>
                        <div class="song-artist" title="${t.artist}">${t.artist}</div>
                    </div>
                `;
                grid.appendChild(card);
            });
        }

        async function searchSong(query) {
            // Try each instance until one succeeds
            for (let i = 0; i < Math.min(instances.length, 6); i++) {
                let instance = instances[i];
                let url = `https://${instance}/api/v1/search?q=${encodeURIComponent(query)}&type=video`;
                try {
                    let controller = new AbortController();
                    let timeoutId = setTimeout(() => controller.abort(), 6000);
                    let res = await fetch(url, { signal: controller.signal });
                    clearTimeout(timeoutId);
                    
                    if (res.ok) {
                        let data = await res.json();
                        if (data && data.length > 0) {
                            return { videoId: data[0].videoId, instance };
                        }
                    }
                } catch (e) {
                    // Try next instance
                }
            }
            return null;
        }

        async function fetchImageAsBlob(videoId, instance) {
            // Try direct YouTube first, fall back to Invidious image proxy if CORS fails
            const urls = [
                `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`,
                `https://${instance}/vi/${videoId}/hqdefault.jpg`,
                `https://img.youtube.com/vi/${videoId}/0.jpg`
            ];
            
            for (let url of urls) {
                try {
                    let controller = new AbortController();
                    let timeoutId = setTimeout(() => controller.abort(), 8000);
                    let res = await fetch(url, { signal: controller.signal });
                    clearTimeout(timeoutId);
                    
                    if (res.ok) {
                        return await res.blob();
                    }
                } catch (e) {
                    // Try next URL
                }
            }
            return null;
        }

        async function processQueue() {
            if (!isRunning) return;
            
            const maxConcurrency = 4;
            while (activeDownloads < maxConcurrency && queue.length > 0) {
                const task = queue.shift();
                activeDownloads++;
                runTask(task);
            }
        }

        async function runTask(task) {
            const { track, index } = task;
            const card = document.getElementById(`card-${index}`);
            const badge = document.getElementById(`badge-${index}`);
            const thumb = document.getElementById(`thumb-${index}`);
            
            card.className = "song-card fetching";
            badge.textContent = "Searching";
            
            log(`Searching YouTube for: "${track.query}"`, "info");
            
            let result = await searchSong(track.query);
            if (result) {
                const { videoId, instance } = result;
                badge.textContent = "Downloading";
                log(`Found videoId ${videoId} using ${instance}. Fetching thumbnail...`, "info");
                
                let blob = await fetchImageAsBlob(videoId, instance);
                if (blob && blob.size > 1000) {
                    const hash = await sha1(track.path);
                    zip.file(`${hash}.jpg`, blob);
                    
                    // Update UI with the downloaded image
                    const url = URL.createObjectURL(blob);
                    thumb.style.backgroundImage = `url(${url})`;
                    thumb.style.backgroundSize = "cover";
                    thumb.style.backgroundPosition = "center";
                    
                    card.className = "song-card success";
                    badge.textContent = "Done";
                    successCount++;
                    log(`Successfully downloaded art for: ${track.title}`, "success");
                } else {
                    card.className = "song-card error";
                    badge.textContent = "Error";
                    errorCount++;
                    log(`Failed to fetch thumbnail for: ${track.title}`, "error");
                }
            } else {
                card.className = "song-card error";
                badge.textContent = "Not Found";
                errorCount++;
                log(`No search results for: ${track.title}`, "error");
            }
            
            completedCount++;
            activeDownloads--;
            updateProgress();
            
            // Recurse to process the next item
            processQueue();
        }

        function updateProgress() {
            const percent = Math.round((completedCount / tracks.length) * 100);
            document.getElementById("progressBar").style.width = `${percent}%`;
            document.getElementById("progressText").textContent = `Completed: ${completedCount}/${tracks.length} (${percent}%)`;
            document.getElementById("statusText").textContent = `Active: ${activeDownloads} | Success: ${successCount} | Failed: ${errorCount}`;
            
            if (completedCount === tracks.length) {
                isRunning = false;
                document.getElementById("statusText").textContent = `Finished! Success: ${successCount} | Failed: ${errorCount}`;
                document.getElementById("downloadBtn").disabled = false;
                log("All downloads completed! Generating ZIP...", "success");
                saveZip(); // Auto-download ZIP!
            }
        }

        async function startDownload() {
            if (isRunning) return;
            isRunning = true;
            document.getElementById("startBtn").disabled = true;
            
            log("Loading Invidious instances...", "info");
            await loadInstances();
            
            log("Starting queue...", "info");
            queue = tracks.map((t, idx) => ({ track: t, index: idx }));
            processQueue();
        }

        function saveZip() {
            log("Packaging covers zip...", "info");
            zip.generateAsync({ type: "blob" }).then((content) => {
                const url = window.URL.createObjectURL(content);
                const a = document.createElement("a");
                a.href = url;
                a.download = "youtube_covers.zip";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                log("ZIP download triggered successfully!", "success");
            });
        }

        window.onload = () => {
            buildQueueUI();
        };
    </script>
</body>
</html>
"""

# Inject track list JSON
html_content = html_content.replace("###TRACKS_JSON###", json.dumps(tracks, ensure_ascii=False))

# Save to file
downloader_path = Path(__file__).parent / "downloader.html"
with open(downloader_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print("Successfully generated downloader.html")
