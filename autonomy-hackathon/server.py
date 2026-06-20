import http.server
import socketserver
import os

# The embedded HTML/CSS/JS Dashboard
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FLIGHT OPS // AUTONOMOUS COMMAND</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --void:#04070c; --panel:#0a1019; --panel-2:#0d1622;
            --grid-line:#15212f; --edge:#1d2d40;
            --phosphor:#45e6d2; --amber:#ffb347; --nominal:#5dd99a; --alert:#ff3b30;
            --text:#c4d4e3; --text-dim:#56697d; --text-ghost:#2c3d4f;
        }
        * { box-sizing: border-box; }
        html, body { height: 100%; overflow: hidden; }
        body {
            margin: 0;
            background:
                radial-gradient(1000px 600px at 50% -12%, #0a1726 0%, transparent 60%),
                repeating-linear-gradient(0deg, transparent 0 31px, rgba(69,230,210,0.015) 31px 32px),
                var(--void);
            color: var(--text);
            font-family: 'Chakra Petch', sans-serif;
            font-size: 13px; letter-spacing: 0.015em;
            -webkit-font-smoothing: antialiased;
            display: flex; flex-direction: column;
            height: 100vh; padding: 10px; gap: 9px;
        }
        .mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }

        /* ---------- NAV ---------- */
        .nav {
            flex: 0 0 auto; display: flex; align-items: center; gap: 16px;
            padding: 0 4px;
        }
        .brand { display: flex; flex-direction: column; line-height: 1; }
        .brand .eyebrow { font-size: 8px; letter-spacing: 0.34em; color: var(--text-dim); text-transform: uppercase; margin-bottom: 3px; }
        .brand h1 { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: 0.05em; }
        .brand h1 .accent { color: var(--phosphor); }
        .nav .spacer { flex: 1; }
        .chip {
            display: flex; flex-direction: column; align-items: flex-end; line-height: 1.1;
            border-left: 1px solid var(--edge); padding-left: 14px;
        }
        .chip .k { font-size: 8px; letter-spacing: 0.2em; color: var(--text-dim); text-transform: uppercase; }
        .chip .v { font-size: 14px; font-weight: 700; color: var(--phosphor); }
        .hbt { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--nominal); box-shadow: 0 0 8px var(--nominal); margin-right: 6px; vertical-align: middle; }
        body[data-link="stalled"] .hbt { background: var(--alert); box-shadow: 0 0 9px var(--alert); }
        body:not([data-link="stalled"]) .hbt { animation: hb 1s ease-in-out infinite; }
        @keyframes hb { 0%,100%{opacity:.35} 50%{opacity:1} }
        .hzmeter { display: flex; gap: 2px; align-items: flex-end; height: 13px; margin-top: 2px; }
        .hzmeter i { width: 3px; background: var(--edge); border-radius: 1px; }
        .audio-btn {
            font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; letter-spacing: 0.1em;
            color: var(--text-dim); background: var(--panel); border: 1px solid var(--edge);
            border-radius: 3px; padding: 7px 10px; cursor: pointer; transition: all .18s ease; white-space: nowrap;
        }
        .audio-btn:hover { color: var(--text); border-color: var(--phosphor); }
        .audio-btn.armed { color: var(--nominal); border-color: rgba(93,217,154,.5); }

        /* ---------- KILL STRIP ---------- */
        .killstrip {
            flex: 0 0 auto; position: relative; width: 100%; min-height: 46px;
            border: none; border-radius: 4px; cursor: pointer; overflow: hidden;
            font-family: 'Chakra Petch', sans-serif; color: #fff; text-transform: uppercase;
            display: flex; align-items: center; justify-content: space-between; padding: 0 20px;
            background: linear-gradient(180deg, #ff5247 0%, #d6261c 55%, #9a1813 100%);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.35), inset 0 -3px 10px rgba(0,0,0,.5),
                        0 4px 0 #6e0f0b, 0 6px 16px rgba(255,59,48,.3);
            transition: transform .06s ease, box-shadow .06s ease, filter .2s ease;
        }
        .killstrip::before {
            content: ""; position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity .2s ease;
            background: repeating-linear-gradient(45deg, rgba(0,0,0,0) 0 12px, rgba(0,0,0,.22) 12px 24px);
        }
        .killstrip:hover::before { opacity: 1; }
        .killstrip:hover { filter: brightness(1.08); }
        .killstrip:focus-visible { outline: 2px solid #fff; outline-offset: 3px; }
        .killstrip:active { transform: translateY(4px); box-shadow: inset 0 1px 0 rgba(255,255,255,.25), inset 0 -2px 8px rgba(0,0,0,.55), 0 1px 0 #6e0f0b; }
        .killstrip .kb-l { display: flex; align-items: center; gap: 12px; }
        .killstrip .kb-main { font-size: 17px; font-weight: 700; letter-spacing: 0.16em; }
        .killstrip .kb-icon { font-size: 18px; }
        .killstrip .kb-sub { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.22em; opacity: .85; }
        .killstrip.fired {
            background: linear-gradient(180deg, #2a3a2f, #16201a);
            box-shadow: inset 0 0 0 1px var(--nominal); transform: translateY(4px); cursor: default;
        }

        /* ---------- MAIN GRID ---------- */
        .main {
            flex: 1 1 auto; min-height: 0;
            display: grid; gap: 9px;
            grid-template-columns: minmax(230px, 1fr) minmax(0, 1.55fr) minmax(258px, 1.05fr);
        }
        .col { display: grid; gap: 9px; min-height: 0; min-width: 0; }
        .col.center { grid-template-rows: minmax(0, 1fr) auto auto; }
        .col.right  { grid-template-rows: auto auto 1fr; }

        .panel {
            position: relative; background: linear-gradient(180deg, var(--panel-2), var(--panel));
            border: 1px solid var(--edge); border-radius: 4px; padding: 10px 12px;
            min-height: 0; min-width: 0; display: flex; flex-direction: column;
        }
        .panel::before, .panel::after { content:""; position:absolute; width:9px; height:9px; border:1.5px solid var(--phosphor); opacity:.5; pointer-events:none; }
        .panel::before { top:-1px; left:-1px; border-right:none; border-bottom:none; }
        .panel::after  { bottom:-1px; right:-1px; border-left:none; border-top:none; }
        .panel > .label {
            font-size: 8px; letter-spacing: 0.26em; text-transform: uppercase; color: var(--text-dim);
            display: flex; align-items: center; gap: 7px; margin-bottom: 8px; flex: 0 0 auto;
        }
        .panel > .label::after { content:""; flex:1; height:1px; background: linear-gradient(90deg, var(--edge), transparent); }
        .label .right { color: var(--text-dim); letter-spacing: .12em; }

        /* ---------- VISION + TAPE ---------- */
        .vision { }
        .feed-wrap { flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 46px; gap: 7px; }
        .feed-frame { position: relative; min-height: 0; background: #060b11; border: 1px solid var(--edge); border-radius: 3px; overflow: hidden; }
        .feed-frame img { width: 100%; height: 100%; object-fit: cover; display: block; filter: saturate(1.05) contrast(1.05); }
        .feed-frame .reticle { position: absolute; inset: 0; pointer-events: none;
            background: linear-gradient(transparent 49.5%, rgba(69,230,210,.16) 50%, transparent 50.5%),
                        linear-gradient(90deg, transparent 49.5%, rgba(69,230,210,.16) 50%, transparent 50.5%); }
        .feed-frame .corner { position: absolute; width: 16px; height: 16px; border: 1.5px solid var(--phosphor); opacity: .7; }
        .c-tl{top:8px;left:8px;border-right:none;border-bottom:none}.c-tr{top:8px;right:8px;border-left:none;border-bottom:none}
        .c-bl{bottom:8px;left:8px;border-right:none;border-top:none}.c-br{bottom:8px;right:8px;border-left:none;border-top:none}
        .feed-frame .scan { position: absolute; left:0; right:0; height:2px; background: linear-gradient(90deg, transparent, rgba(69,230,210,.5), transparent); animation: scan 3.4s linear infinite; }
        @keyframes scan { 0%{top:0} 100%{top:100%} }
        .feed-tag { position:absolute; bottom:8px; left:10px; font-family:'JetBrains Mono',monospace; font-size:9px; letter-spacing:.18em; color:var(--phosphor); background:rgba(4,7,12,.6); padding:2px 6px; border-radius:2px; }
        .feed-frame.nosignal img { display:none; }
        .feed-frame.nosignal::after { content:"NO SIGNAL"; position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:.2em; color:var(--text-dim); background: repeating-linear-gradient(0deg, transparent 0 3px, rgba(255,255,255,.025) 3px 4px); }
        .tape { position: relative; background:#060b11; border:1px solid var(--edge); border-radius:3px; overflow:hidden; font-family:'JetBrains Mono',monospace; }
        .tape .tl { position:absolute; top:4px; left:0; right:0; text-align:center; font-size:7px; letter-spacing:.14em; color:var(--text-dim); z-index:3; }
        .tape .fill { position:absolute; left:0; right:0; bottom:0; background: linear-gradient(180deg, rgba(69,230,210,.42), rgba(69,230,210,.08)); border-top:1.5px solid var(--phosphor); transition:height .18s ease; z-index:1; }
        .tape .ticks .t { position:absolute; right:3px; font-size:7px; color:var(--text-ghost); transform:translateY(50%); z-index:2; }
        .tape .ptr { position:absolute; left:0; right:0; z-index:4; transition:bottom .18s ease; display:flex; justify-content:center; }
        .tape .ptr .box { background:var(--phosphor); color:#04181a; font-weight:800; font-size:10px; padding:1px 3px; border-radius:2px; transform:translateY(-50%); }

        /* ---------- ALTITUDE GRAPH ---------- */
        .altgraph .head { display:flex; justify-content:space-between; align-items:baseline; gap:10px; margin-bottom:4px; flex:0 0 auto; }
        .altgraph .now { font-family:'JetBrains Mono',monospace; font-variant-numeric:tabular-nums; font-size:26px; font-weight:800; color:var(--phosphor); line-height:1; text-shadow:0 0 14px rgba(69,230,210,.25); }
        .altgraph .now .u { font-size:11px; color:var(--text-dim); margin-left:3px; }
        .altgraph .stats { display:flex; gap:14px; font-family:'JetBrains Mono',monospace; }
        .altgraph .stats .k { font-size:8px; letter-spacing:.16em; color:var(--text-dim); text-transform:uppercase; }
        .altgraph .stats .v { font-size:14px; font-weight:700; color:var(--amber); }
        .graphbox { position: relative; flex: 1; min-height: 0; padding-left: 26px; padding-bottom: 14px; }
        .graphbox svg { position:absolute; inset:0 0 14px 26px; width:calc(100% - 26px); height:calc(100% - 14px); }
        .graphbox .ygrid span { position:absolute; left:0; transform:translateY(-50%); font-size:8px; color:var(--text-ghost); font-family:'JetBrains Mono',monospace; }
        .graphbox .xlabel { position:absolute; bottom:0; left:26px; right:0; text-align:center; font-size:8px; letter-spacing:.14em; color:var(--text-ghost); font-family:'JetBrains Mono',monospace; }
        #alt_line { fill:none; stroke:var(--phosphor); stroke-width:2; }
        #alt_area { fill: rgba(69,230,210,.10); stroke:none; }

        /* ---------- AVIONICS / DIAGNOSTICS ---------- */
        .avionics .grid { flex:1; min-height:70px; display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; }
        .ecu .grid { flex:1; min-height:70px; display:grid; grid-template-columns: repeat(2, 1fr); gap:8px; }
        .avx { border:1px solid var(--edge); border-radius:3px; background:var(--panel); padding:9px 11px; display:flex; flex-direction:column; justify-content:center; gap:5px; min-width:0; overflow:hidden; }
        .avx .k { font-size:8px; letter-spacing:.16em; color:var(--text-dim); text-transform:uppercase; display:flex; align-items:center; line-height:1.25; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .avx .k .dot { flex:0 0 auto; width:5px; height:5px; border-radius:50%; background:var(--nominal); box-shadow:0 0 4px var(--nominal); margin-right:8px; }
        .avx .v { font-family:'JetBrains Mono',monospace; font-variant-numeric:tabular-nums; font-size:16px; font-weight:800; color:var(--phosphor); line-height:1.15; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .avx .v.amber { color:var(--amber); font-size:13px; }
        .avx .battbar { height:4px; border-radius:2px; background:var(--edge); overflow:hidden; }
        .avx .battbar i { display:block; height:100%; background:var(--nominal); transition:width .25s ease, background .25s ease; }

        /* ---------- WATCHDOG ---------- */
        .watchdog { align-items:center; justify-content:center; text-align:center; border:1px solid var(--edge);
            transition: background .25s ease, border-color .25s ease; }
        .watchdog .wd-top { display:flex; align-items:center; justify-content:center; gap:9px; }
        .watchdog .ring { flex:0 0 auto; width:11px; height:11px; border-radius:50%; }
        .watchdog .state { font-size:22px; font-weight:700; letter-spacing:.05em; line-height:1; }
        .watchdog .sub { font-family:'JetBrains Mono',monospace; font-size:9px; letter-spacing:.2em; color:var(--text-dim); margin-top:6px; }
        body:not([data-link="stalled"]) .watchdog { border-color: rgba(93,217,154,.35); }
        body:not([data-link="stalled"]) .watchdog .state { color: var(--nominal); }
        body:not([data-link="stalled"]) .watchdog .ring { background:var(--nominal); animation: wd 2.4s ease-out infinite; }
        @keyframes wd { 0%{box-shadow:0 0 0 0 rgba(93,217,154,.55)} 70%{box-shadow:0 0 0 13px rgba(93,217,154,0)} 100%{box-shadow:0 0 0 0 rgba(93,217,154,0)} }
        body[data-link="stalled"] .watchdog { border-color:var(--alert); background:rgba(255,59,48,.06); animation: wdf .7s steps(1,end) infinite; }
        body[data-link="stalled"] .watchdog .state { color:var(--alert); }
        body[data-link="stalled"] .watchdog .ring { background:var(--alert); box-shadow:0 0 12px var(--alert); }
        @keyframes wdf { 0%,49%{background:rgba(255,59,48,.15); box-shadow:inset 0 0 45px rgba(255,59,48,.25)} 50%,100%{background:rgba(255,59,48,.02)} }
        .alarm-flood { position:fixed; inset:0; pointer-events:none; z-index:50; opacity:0; transition:opacity .2s ease; }
        body[data-link="stalled"] .alarm-flood { opacity:1; box-shadow: inset 0 0 150px 26px rgba(255,59,48,.26); animation: flood .9s ease-in-out infinite; }
        @keyframes flood { 0%,100%{opacity:.35} 50%{opacity:1} }

        /* ---------- METRIC CARDS ---------- */
        .metrics { display:grid; grid-template-columns: repeat(2,1fr); gap:9px; min-height:0; }
        .metric { border:1px solid var(--edge); border-radius:4px; background: linear-gradient(180deg, var(--panel-2), var(--panel)); padding:8px 10px; position:relative; }
        .metric .k { font-size:8px; letter-spacing:.22em; color:var(--text-dim); text-transform:uppercase; }
        .metric .v { font-family:'JetBrains Mono',monospace; font-variant-numeric:tabular-nums; font-weight:800; line-height:1; margin-top:5px; }
        .metric .v .u { font-size:10px; color:var(--text-dim); margin-left:2px; }
        .metric.alt .v, .metric.spd .v { font-size:21px; color:var(--phosphor); }
        .metric.st .v { font-size:15px; color:var(--amber); }

        /* ---------- DECISION LOG ---------- */
        .log .meta { display:grid; grid-template-columns:1fr 1fr; gap:7px; margin-bottom:8px; flex:0 0 auto; }
        .log .meta .cell { border:1px solid var(--edge); border-radius:3px; padding:6px 9px; background:var(--panel); }
        .log .meta .k { font-size:8px; letter-spacing:.2em; color:var(--text-dim); text-transform:uppercase; }
        .log .meta .v { font-family:'JetBrains Mono',monospace; font-size:14px; font-weight:700; color:var(--amber); margin-top:2px; word-break:break-word; }
        .terminal { flex:1; min-height:0; overflow-y:auto; font-family:'JetBrains Mono',monospace; font-size:11px; line-height:1.6;
            background:#050a10; border:1px solid var(--edge); border-radius:3px; padding:8px 10px; }
        .terminal .line { white-space:nowrap; }
        .terminal .ts { color:var(--text-ghost); margin-right:8px; }
        .terminal .arrow { color:var(--phosphor); margin-right:6px; }
        .terminal::-webkit-scrollbar { width:6px; }
        .terminal::-webkit-scrollbar-thumb { background:var(--edge); border-radius:3px; }

        /* ---------- TOAST ---------- */
        .toast { position:fixed; bottom:18px; left:50%; transform:translateX(-50%) translateY(160%);
            background:linear-gradient(180deg,#d6261c,#9a1813); color:#fff; font-family:'JetBrains Mono',monospace;
            font-weight:700; letter-spacing:.14em; padding:11px 22px; border-radius:4px; font-size:12px;
            box-shadow:0 10px 30px rgba(255,59,48,.45); z-index:60; transition:transform .32s cubic-bezier(.2,.9,.25,1); }
        .toast.show { transform:translateX(-50%) translateY(0); }

        @media (prefers-reduced-motion: reduce) {
            * { animation-duration:.001ms !important; animation-iteration-count:1 !important; }
            body[data-link="stalled"] .watchdog { background: rgba(255,59,48,.12); }
            body[data-link="stalled"] .alarm-flood { opacity:1; }
        }
    </style>
</head>
<body data-link="init">

    <div class="alarm-flood"></div>

    <!-- NAV -->
    <header class="nav">
        <div class="brand">
            <div class="eyebrow">Autonomous Flight Ops &middot; Comms-Denied</div>
            <h1>FLIGHT <span class="accent">COMMAND</span></h1>
        </div>
        <div class="spacer"></div>
        <div class="chip"><span class="k">Datalink</span><span class="v mono"><span class="hbt"></span><span id="link_txt">--</span></span></div>
        <div class="chip"><span class="k">Mission Clock</span><span class="v mono" id="clock">00:00:00</span></div>
        <div class="chip"><span class="k">Link Rate</span><span class="v mono" id="hz">0.0 Hz</span><span class="hzmeter" id="hz_bars"></span></div>
        <button class="audio-btn" id="audio_btn" onclick="toggleAudio()">&#128263; ALARM OFF</button>
    </header>

    <!-- KILL STRIP -->
    <button class="killstrip" id="kill_btn" onclick="triggerKillSwitch()" aria-label="Emergency kill switch">
        <span class="kb-l"><span class="kb-icon">&#9888;</span><span class="kb-main">EMERGENCY KILL SWITCH</span></span>
        <span class="kb-sub" id="kill_sub">SAFETY ARMED &middot; CUTS MOTORS &middot; IRREVERSIBLE</span>
    </button>

    <!-- MAIN -->
    <main class="main">

        <!-- LEFT: VISION -->
        <section class="col left">
            <div class="panel vision">
                <div class="label">Vision Pipeline &middot; Targeting</div>
                <div class="feed-wrap">
                    <div class="feed-frame" id="feed_frame">
                        <img id="vision_feed" src="latest_mask.jpg" alt="Vision mask feed"
                             onload="document.getElementById('feed_frame').classList.remove('nosignal')"
                             onerror="document.getElementById('feed_frame').classList.add('nosignal')">
                        <div class="reticle"></div>
                        <span class="corner c-tl"></span><span class="corner c-tr"></span>
                        <span class="corner c-bl"></span><span class="corner c-br"></span>
                        <div class="scan"></div>
                        <div class="feed-tag">SEG-MASK &middot; LIVE</div>
                    </div>
                    <div class="tape" id="tape">
                        <div class="tl">ALT</div>
                        <div class="fill" id="tape_fill" style="height:0%"></div>
                        <div class="ticks" id="tape_ticks"></div>
                        <div class="ptr" id="tape_ptr" style="bottom:0%"><span class="box" id="tape_val">0.0</span></div>
                    </div>
                </div>
            </div>
        </section>

        <!-- CENTER: GRAPH + AVIONICS -->
        <section class="col center">
            <div class="panel altgraph">
                <div class="label">Altitude Profile <span class="right" id="graph_window">LAST 48 TICKS</span></div>
                <div class="head">
                    <div class="now"><span id="alt_now">0.00</span><span class="u">m AGL</span></div>
                    <div class="stats">
                        <div><div class="k">Peak</div><div class="v" id="alt_peak">0.00</div></div>
                        <div><div class="k">Min</div><div class="v" id="alt_min">0.00</div></div>
                    </div>
                </div>
                <div class="graphbox">
                    <div class="ygrid" id="ygrid"></div>
                    <svg id="altsvg" viewBox="0 0 640 240" preserveAspectRatio="none">
                        <g id="alt_grid"></g>
                        <path id="alt_area"></path>
                        <polyline id="alt_line" vector-effect="non-scaling-stroke"></polyline>
                        <circle id="alt_dot" r="3" fill="var(--phosphor)"></circle>
                    </svg>
                    <div class="xlabel">RELATIVE TIME (TICKS) &#8594;</div>
                </div>
            </div>

            <div class="panel avionics">
                <div class="label">Avionics &middot; Sub-Systems</div>
                <div class="grid">
                    <div class="avx">
                        <div class="k"><span class="dot"></span>,,Battery</div>
                        <div class="v" id="battery">100%</div>
                        <div class="battbar"><i id="batt_bar" style="width:100%"></i></div>
                    </div>
                    <div class="avx">
                        <div class="k"><span class="dot"></span>,,IMU1 &middot; Attitude</div>
                        <div class="v amber" id="imu">P: 0.0 | R: 0.0</div>
                    </div>
                    <div class="avx">
                        <div class="k"><span class="dot"></span>,,Barometer1</div>
                        <div class="v" id="barometer">1013 hPa</div>
                    </div>
                </div>
            </div>

            <div class="panel ecu">
                <div class="label">Edge Compute &amp; Link Diagnostics</div>
                <div class="grid">
                    <div class="avx"><div class="k"><span class="dot"></span>,,Link Latency</div><div class="v" id="latency">12 ms</div></div>
                    <div class="avx"><div class="k"><span class="dot"></span>,,Packet Loss</div><div class="v" id="packetloss">0.01%</div></div>
                    <div class="avx"><div class="k"><span class="dot"></span>,,Core Temp</div><div class="v" id="coretemp">42&deg;C</div></div>
                    <div class="avx"><div class="k"><span class="dot"></span>,,Rotor RPM</div><div class="v amber" id="rpm">M1: 4020 | M2: 3980</div></div>
                </div>
            </div>
        </section>

        <!-- RIGHT: WATCHDOG + METRICS + LOG -->
        <section class="col right">
            <div class="panel watchdog" id="watchdog_panel">
                <div class="wd-top"><span class="ring"></span><span class="state" id="watchdog">HEALTHY</span></div>
                <div class="sub" id="watchdog_sub">LAST PACKET 0.0s AGO</div>
            </div>

            <div class="metrics">
                <div class="metric st"><div class="k">Status</div><div class="v" id="status">WAIT</div></div>
                <div class="metric spd"><div class="k">Speed</div><div class="v"><span id="speed">0.00</span><span class="u">m/s</span></div></div>
            </div>

            <div class="panel log">
                <div class="label">Decision Log</div>
                <div class="meta">
                    <div class="cell"><div class="k">Last Clue</div><div class="v" id="clue">None</div></div>
                    <div class="cell"><div class="k">Spheres</div><div class="v" id="spheres">0</div></div>
                </div>
                <div class="terminal" id="terminal">
                    <div class="line"><span class="ts">--:--:--</span><span class="arrow">&gt;</span>console standby</div>
                </div>
            </div>
        </section>

    </main>

    <div class="toast" id="toast">&#9888; EMERGENCY SIGNAL TRANSMITTED</div>

    <script>
        let lastUpdateTime = Date.now();
        const bootTime = Date.now();
        let lastDecision = null;
        let killed = false;
        const altHist = [], spdHist = [], MAX_PTS = 48;
        let altPeak = -Infinity, altMin = Infinity;
        const recvTimes = [];

        // clock
        setInterval(() => {
            const t = Math.floor((Date.now() - bootTime) / 1000);
            const p = n => String(n).padStart(2,'0');
            document.getElementById('clock').innerText = p(Math.floor(t/3600))+':'+p(Math.floor(t%3600/60))+':'+p(t%60);
        }, 1000);

        // audio
        let audioCtx = null, alarmArmed = false, lastBeepAt = 0;
        function toggleAudio() {
            const b = document.getElementById('audio_btn');
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            if (audioCtx.state === 'suspended') audioCtx.resume();
            alarmArmed = !alarmArmed;
            b.classList.toggle('armed', alarmArmed);
            b.innerHTML = alarmArmed ? '&#128266; ALARM ARMED' : '&#128263; ALARM OFF';
        }
        function beep(freq, dur, type, vol) {
            if (!audioCtx || !alarmArmed) return;
            const o = audioCtx.createOscillator(), g = audioCtx.createGain();
            o.type = type || 'square'; o.frequency.value = freq; g.gain.value = vol || 0.06;
            o.connect(g); g.connect(audioCtx.destination);
            const t = audioCtx.currentTime; o.start(t);
            g.gain.exponentialRampToValueAtTime(0.0001, t + dur); o.stop(t + dur);
        }

        // altitude graph (stretched viewBox + HTML y-labels)
        const GY0 = 10, GY1 = 230, GX0 = 4, GX1 = 636;
        const niceMax = v => v <= 10 ? 10 : Math.ceil(v/5)*5;
        function renderGraph() {
            const ceil = niceMax(altPeak === -Infinity ? 0 : altPeak);
            let g = '', yl = '', rows = 4;
            for (let i = 0; i <= rows; i++) {
                const y = GY0 + (GY1 - GY0) * i / rows;
                g += '<line x1="'+GX0+'" y1="'+y+'" x2="'+GX1+'" y2="'+y+'" stroke="var(--grid-line)" stroke-width="1" vector-effect="non-scaling-stroke"/>';
                yl += '<span style="top:'+(y/240*100)+'%">'+(ceil*(rows-i)/rows).toFixed(0)+'</span>';
            }
            document.getElementById('alt_grid').innerHTML = g;
            document.getElementById('ygrid').innerHTML = yl;
            if (altHist.length < 2) return;
            const step = (GX1 - GX0) / (MAX_PTS - 1);
            const pts = altHist.map((v, i) => {
                const x = GX0 + i * step;
                const y = Math.max(GY0, Math.min(GY1, GY1 - (v/ceil)*(GY1-GY0)));
                return x.toFixed(1)+','+y.toFixed(1);
            });
            document.getElementById('alt_line').setAttribute('points', pts.join(' '));
            const fx = pts[0].split(',')[0], lx = pts[pts.length-1].split(',')[0];
            document.getElementById('alt_area').setAttribute('d','M'+fx+','+GY1+' L'+pts.join(' L')+' L'+lx+','+GY1+' Z');
            const xy = pts[pts.length-1].split(',');
            const dot = document.getElementById('alt_dot'); dot.setAttribute('cx', xy[0]); dot.setAttribute('cy', xy[1]);
        }

        // altitude tape
        function renderTape(alt) {
            const ceil = niceMax(altPeak === -Infinity ? 0 : altPeak);
            const pct = Math.max(0, Math.min(100, alt/ceil*100));
            document.getElementById('tape_fill').style.height = pct+'%';
            document.getElementById('tape_ptr').style.bottom = pct+'%';
            document.getElementById('tape_val').innerText = alt.toFixed(1);
            const box = document.getElementById('tape_ticks');
            let h = '';
            for (let i = 0; i <= 4; i++) h += '<span class="t" style="bottom:'+(i/4*100)+'%">'+(ceil*i/4).toFixed(0)+'</span>';
            box.innerHTML = h;
        }
        function pushHist(a, v) { a.push(v); if (a.length > MAX_PTS) a.shift(); }

        // link rate
        function renderLinkQuality() {
            const cut = Date.now() - 1000;
            while (recvTimes.length && recvTimes[0] < cut) recvTimes.shift();
            const hz = recvTimes.length;
            document.getElementById('hz').innerText = hz.toFixed(1) + ' Hz';
            const bars = document.getElementById('hz_bars');
            if (!bars.children.length) for (let i=0;i<6;i++) bars.appendChild(document.createElement('i'));
            const lit = Math.round(Math.min(hz,4)/4*6);
            const color = hz === 0 ? 'var(--alert)' : (hz < 3 ? 'var(--amber)' : 'var(--nominal)');
            [...bars.children].forEach((b,i) => { b.style.height = (40 + i*10)+'%'; b.style.background = i < lit ? color : 'var(--edge)'; });
        }

        // terminal
        function logEvent(text) {
            const term = document.getElementById('terminal');
            const ts = new Date().toTimeString().slice(0,8);
            const line = document.createElement('div'); line.className = 'line';
            line.innerHTML = '<span class="ts">'+ts+'</span><span class="arrow">&gt;</span>'+text;
            term.appendChild(line);
            if (term.children.length > 60) term.removeChild(term.firstChild);
            term.scrollTop = term.scrollHeight;
        }

        function setLinkState(s) {
            document.body.setAttribute('data-link', s);
            if (s === 'stalled') { document.getElementById('watchdog').innerText = 'STALLED'; document.getElementById('link_txt').innerText = 'LOST'; }
            else { document.getElementById('watchdog').innerText = 'HEALTHY'; document.getElementById('link_txt').innerText = 'NOMINAL'; }
        }

        // telemetry poll
        function updateDashboard() {
            fetch('telemetry.json?' + new Date().getTime())
                .then(r => r.json())
                .then(data => {
                    const alt = data.altitude || 0, spd = data.speed || 0;
                    document.getElementById('status').innerText = (data.status || 'UNKNOWN').toUpperCase();
                    document.getElementById('alt_now').innerText = alt.toFixed(2);
                    document.getElementById('speed').innerText = spd.toFixed(2);
                    document.getElementById('clue').innerText = data.last_decision || 'None';
                    document.getElementById('spheres').innerText = data.spheres_seen || 0;

                    // --- New Avionics telemetry (safe fallbacks) ---
                    document.getElementById('battery').innerText = data.battery || "100%";
                    document.getElementById('imu').innerText = data.imu || "P: 0.0 | R: 0.0";
                    document.getElementById('barometer').innerText = data.barometer || "1013 hPa";

                    // --- Edge compute & link diagnostics (static placeholders until backend sends them) ---
                    document.getElementById('latency').innerText = data.latency || "12 ms";
                    document.getElementById('packetloss').innerText = data.packet_loss || "0.01%";
                    document.getElementById('coretemp').innerText = data.core_temp || "42\\u00b0C";
                    document.getElementById('rpm').innerText = data.rpm || "M1: 4020 | M2: 3980";

                    // drive the battery bar only when value is a percentage
                    const bv = data.battery || "100%";
                    const bm = (''+bv).match(/(\\d+(?:\\.\\d+)?)\\s*%/);
                    const bar = document.getElementById('batt_bar');
                    if (bm) {
                        const p = Math.max(0, Math.min(100, parseFloat(bm[1])));
                        bar.style.width = p + '%';
                        bar.style.background = p < 20 ? 'var(--alert)' : (p < 40 ? 'var(--amber)' : 'var(--nominal)');
                    }

                    altPeak = Math.max(altPeak, alt); altMin = Math.min(altMin, alt);
                    document.getElementById('alt_peak').innerText = altPeak.toFixed(2);
                    document.getElementById('alt_min').innerText = (altMin === Infinity ? 0 : altMin).toFixed(2);

                    pushHist(altHist, alt); pushHist(spdHist, spd);
                    renderGraph(); renderTape(alt);

                    const d = data.last_decision || null;
                    if (d && d !== lastDecision) { logEvent('DECISION :: '+d+'  [spheres='+(data.spheres_seen||0)+']'); lastDecision = d; }

                    recvTimes.push(Date.now()); lastUpdateTime = Date.now();
                    setLinkState('healthy');
                    document.getElementById('vision_feed').src = 'latest_mask.jpg?' + new Date().getTime();
                })
                .catch(() => console.log('Waiting for telemetry...'));
        }

        // watchdog (2s)
        setInterval(() => {
            const age = (Date.now() - lastUpdateTime) / 1000;
            document.getElementById('watchdog_sub').innerText = 'LAST PACKET ' + age.toFixed(1) + 's AGO';
            renderLinkQuality();
            if (age > 2) {
                if (document.body.getAttribute('data-link') !== 'stalled') logEvent('WATCHDOG :: datalink stalled — telemetry > 2.0s old');
                setLinkState('stalled');
                const now = Date.now();
                if (now - lastBeepAt > 1100) { beep(880, 0.18, 'square', 0.07); lastBeepAt = now; }
            }
        }, 250);

        setInterval(updateDashboard, 250);

        // kill switch
        function triggerKillSwitch() {
            if (killed) return; killed = true;
            const btn = document.getElementById('kill_btn'), sub = document.getElementById('kill_sub'), toast = document.getElementById('toast');
            beep(440, 0.25, 'sawtooth', 0.09); setTimeout(() => beep(300, 0.35, 'sawtooth', 0.09), 180);
            fetch('/kill', { method: 'POST' })
                .then(() => {
                    btn.classList.add('fired');
                    btn.querySelector('.kb-main').innerText = 'ABORT SENT — MOTORS CUT';
                    sub.innerText = 'SIGNAL DELIVERED';
                    logEvent('OPERATOR :: EMERGENCY KILL SWITCH ENGAGED');
                    toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 3200);
                })
                .catch(() => { killed = false; sub.innerText = 'TRANSMIT FAILED — RETRY'; logEvent('OPERATOR :: KILL TRANSMIT FAILED — retry'); });
        }
    </script>
</body>
</html>
"""

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Serve the HTML page on the root URL
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        else:
            # Serve the images and JSON files naturally
            super().do_GET()

    def do_POST(self):
        # Handle the Kill Switch button press
        if self.path == '/kill':
            with open("EMERGENCY_STOP.flag", "w") as f:
                f.write("ABORT")
            self.send_response(200)
            self.end_headers()

# Start the server on port 8000
PORT = 8000
with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
    print(f"✅ Command Center live! Open your browser to: http://localhost:{PORT}")
    httpd.serve_forever()