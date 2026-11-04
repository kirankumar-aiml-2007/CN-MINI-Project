#!/usr/bin/env python3
"""
SDN Distributed Backup - Control Dashboard
Run the controller first, then (from the project root):
    sudo python3 gui/dashboard.py
Open http://localhost:8080
"""
import os, sys, json, threading, subprocess, importlib.util, time, collections
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.makedirs("uploads", exist_ok=True)

# Load mininet/topo.py by path (its folder name clashes with the mininet package)
spec = importlib.util.spec_from_file_location("project_topo", os.path.join(ROOT, "mininet", "topo.py"))
topo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(topo)

IPS = {"h2": "10.0.0.2", "h3": "10.0.0.3"}
SW_LINKS = [("s1", "s2"), ("s1", "s3"), ("s3", "s2")]
net = None
lock = threading.Lock()
procs, link_up = {}, {f"{a}-{b}": True for a, b in SW_LINKS}
logs = collections.deque(maxlen=400)
job = {"running": False, "results": [], "target": []}


def log(src, msg, level="info"):
    logs.append({"t": time.strftime("%H:%M:%S"), "src": src, "msg": msg, "lvl": level})


def pump(name, proc, on_done=None):
    for line in proc.stdout:
        line = line.rstrip()
        if line.strip("= "):
            lvl = "err" if ("ERROR" in line or "✗" in line) else "ok" if "✓" in line else "info"
            log(name, line, lvl)
    proc.wait()
    if on_done:
        on_done(proc.returncode)


def start_server(name):
    if name in procs and procs[name].poll() is None:
        return
    p = net.get(name).popen(["python3", "-u", "-m", "server.server", "0.0.0.0", "5000", f"backup/{name}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    procs[name] = p
    threading.Thread(target=pump, args=(name, p), daemon=True).start()
    log("system", f"Backup server started on {name} ({IPS[name]}:5000)", "ok")


def stop_server(name):
    p = procs.get(name)
    if p and p.poll() is None:
        p.terminate()
        log("system", f"Backup server stopped on {name}", "warn")


def send(path, targets):
    job.update(running=True, results=[], target=targets)

    def done(code):
        job.update(running=False, results=[{"ok": code == 0}])
        log("client", "All backups verified" if code == 0 else "Backup finished with failures",
            "ok" if code == 0 else "err")

    cmd = ["python3", "-u", "-m", "client.client", path] + [f"{IPS[t]}:5000" for t in targets]
    p = net.get("h1").popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    threading.Thread(target=pump, args=("client", p, done), daemon=True).start()


def list_backups():
    out = {}
    for h in IPS:
        d = os.path.join("backup", h)
        out[h] = [{"name": f, "size": os.path.getsize(os.path.join(d, f))}
                  for f in sorted(os.listdir(d)) if not f.endswith(".part")] if os.path.isdir(d) else []
    return out


def flows():
    res = {}
    for s in ("s1", "s2", "s3"):
        r = subprocess.run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", s], capture_output=True, text=True)
        lines = [l.strip() for l in r.stdout.splitlines() if "priority" in l]
        res[s] = [l.split(" ", 1)[-1] if "cookie" in l and False else l for l in lines]
    return res


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            b = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path == "/api/state":
            self.send_json({"links": link_up,
                            "servers": {h: bool(procs.get(h) and procs[h].poll() is None) for h in IPS},
                            "backups": list_backups(), "job": job, "logs": list(logs)[-150:]})
        elif u.path == "/api/flows":
            self.send_json(flows())
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        try:
            if u.path == "/api/upload":
                name = os.path.basename(parse_qs(u.query)["name"][0])
                p = os.path.join("uploads", name)
                open(p, "wb").write(body)
                log("system", f"Uploaded {name} ({len(body)} bytes)")
                return self.send_json({"path": p})
            d = json.loads(body or b"{}")
            with lock:
                if u.path == "/api/server":
                    (start_server if d["action"] == "start" else stop_server)(d["host"])
                elif u.path == "/api/link":
                    a, b = d["link"].split("-")
                    st = "up" if d["up"] else "down"
                    net.configLinkStatus(a, b, st)
                    link_up[d["link"]] = d["up"]
                    log("network", f"Link {a}-{b} set {st.upper()}", "ok" if d["up"] else "err")
                elif u.path == "/api/discover":
                    log("network", "Discovering hosts (ping all)...")
                    loss = net.pingAll(timeout="1")
                    log("network", f"Discovery complete, packet loss {loss:.0f}%", "ok")
                elif u.path == "/api/send":
                    if job["running"]:
                        return self.send_json({"error": "A transfer is already running"}, 409)
                    send(d["path"], d["targets"])
            self.send_json({"ok": True})
        except Exception as e:
            log("system", f"Request failed: {e}", "err")
            self.send_json({"error": str(e)}, 500)


PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SDN Backup Dashboard</title>
<style>
:root{--bg:#0b1220;--card:#131c2e;--line:#22304a;--tx:#e6ecf5;--mut:#8a99b3;--ac:#4f8cff;--ok:#2ecc8f;--err:#ff5d6c;--warn:#f5b84b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.5 system-ui,Segoe UI,sans-serif}
header{display:flex;align-items:center;gap:12px;padding:16px 28px;border-bottom:1px solid var(--line);background:#0e1627}
header h1{font-size:17px;margin:0}header span{color:var(--mut);font-size:12px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok)}
main{display:grid;grid-template-columns:1.3fr 1fr;gap:16px;padding:20px 28px;max-width:1400px;margin:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card h2{margin:0 0 12px;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut)}
.full{grid-column:1/-1}button{background:var(--ac);color:#fff;border:0;border-radius:8px;padding:8px 14px;font-weight:600;cursor:pointer}
button.g{background:#1d2a44;color:var(--tx)}button:disabled{opacity:.4;cursor:not-allowed}button:hover:not(:disabled){filter:brightness(1.12)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.pill{padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600}
.on{background:#12382c;color:var(--ok)}.off{background:#3a1b22;color:var(--err)}
#drop{border:2px dashed var(--line);border-radius:10px;padding:22px;text-align:center;color:var(--mut);cursor:pointer}
#drop.has{border-color:var(--ac);color:var(--tx)}
label.t{display:flex;gap:8px;align-items:center;background:#0e1627;border:1px solid var(--line);padding:8px 12px;border-radius:8px}
#log{height:260px;overflow:auto;background:#0a0f1b;border-radius:8px;padding:10px;font:12px ui-monospace,Consolas,monospace}
.ok{color:var(--ok)}.err{color:var(--err)}.warn{color:var(--warn)}.src{color:var(--ac)}
svg text{fill:var(--tx);font-size:12px;text-anchor:middle}.lk{stroke-width:4;stroke-linecap:round;cursor:pointer}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);font-size:13px}
pre{margin:0;max-height:200px;overflow:auto;font-size:11px;color:var(--mut);white-space:pre-wrap}
@media(max-width:900px){main{grid-template-columns:1fr}}
</style></head><body>
<header><div class="dot"></div><div><h1>SDN Distributed Backup System</h1><span>OS-Ken controller · Mininet · TCP replication with SHA-256 verification</span></div></header>
<main>
<section class="card"><h2>Network topology <span style="text-transform:none;letter-spacing:0">(click a switch link to fail / restore it)</span></h2>
<svg id="topo" viewBox="0 0 520 330" width="100%"></svg>
<div class="row" style="margin-top:8px"><button class="g" onclick="post('/api/discover')">Discover hosts</button>
<button class="g" onclick="showFlows()">Refresh flow tables</button></div></section>

<section class="card"><h2>Backup servers</h2><div id="servers"></div>
<h2 style="margin-top:18px">Send backup (from h1)</h2>
<div id="drop" onclick="fi.click()">Click to choose a file to back up</div><input id="fi" type="file" hidden>
<div class="row" style="margin:12px 0" id="targets"></div>
<button id="sendBtn" onclick="sendFile()">Start backup</button> <span id="jobst" style="color:var(--mut)"></span></section>

<section class="card"><h2>Stored backups</h2><table id="bk"></table></section>
<section class="card"><h2>OpenFlow rules (priority 10 = routed paths)</h2><pre id="flows">Click "Refresh flow tables"</pre></section>
<section class="card full"><h2>Live activity log</h2><div id="log"></div></section>
</main>
<script>
const $=id=>document.getElementById(id);let file=null,S={};
const POS={h1:[110,50],s1:[260,50],s2:[130,190],s3:[390,190],h2:[60,290],h3:[200,290]};
const EDGES=[["h1","s1"],["s2","h2"],["s2","h3"],["s1","s2"],["s1","s3"],["s3","s2"]];
async function post(u,d){const r=await fetch(u,{method:"POST",body:JSON.stringify(d||{})});const j=await r.json();if(j.error)alert(j.error);return j}
function drawTopo(){let h="";for(const[a,b]of EDGES){const k=a+"-"+b,sw=S.links&&k in S.links,up=!sw||S.links[k];
h+=`<line class="lk" x1="${POS[a][0]}" y1="${POS[a][1]}" x2="${POS[b][0]}" y2="${POS[b][1]}" stroke="${up?'#2ecc8f':'#ff5d6c'}" stroke-dasharray="${up?'':'8 6'}" ${sw?`onclick="post('/api/link',{link:'${k}',up:${!up}})"`:'style="cursor:default"'}/>`}
for(const n in POS){const[x,y]=POS[n],host=n[0]=="h",on=S.servers&&S.servers[n];
h+=host?`<rect x="${x-26}" y="${y-16}" width="52" height="32" rx="7" fill="#1d2a44" stroke="${on?'#2ecc8f':'#4f8cff'}" stroke-width="2"/>`:`<circle cx="${x}" cy="${y}" r="22" fill="#4f8cff"/>`;
h+=`<text x="${x}" y="${y+4}">${n}</text>`;if(n=="h1")h+=`<text x="${x}" y="${y+32}" style="fill:#8a99b3">client</text>`;if(IPS[n])h+=`<text x="${x}" y="${y+32}" style="fill:#8a99b3">${IPS[n]}</text>`}
$("topo").innerHTML=h}
const IPS={h2:"10.0.0.2",h3:"10.0.0.3"};
function render(){drawTopo();
$("servers").innerHTML=Object.keys(IPS).map(h=>{const on=S.servers[h];return `<div class="row" style="margin-bottom:8px"><b style="width:30px">${h}</b><span style="color:var(--mut)">${IPS[h]}:5000</span><span class="pill ${on?'on':'off'}">${on?'RUNNING':'STOPPED'}</span><span style="flex:1"></span><button class="g" onclick="post('/api/server',{host:'${h}',action:'${on?'stop':'start'}'})">${on?'Stop':'Start'}</button></div>`}).join("");
const sel=[...document.querySelectorAll(".tg:checked")].map(e=>e.value);
if(!$("targets").children.length||!$("targets").dataset.i){$("targets").dataset.i=1;$("targets").innerHTML=Object.keys(IPS).map(h=>`<label class="t"><input class="tg" type="checkbox" value="${h}" checked>${h}</label>`).join("")}
$("sendBtn").disabled=!file||S.job.running;$("jobst").textContent=S.job.running?"Transfer in progress...":"";
let r="<tr><th>Server</th><th>File</th><th>Size</th></tr>";
for(const h in S.backups)for(const f of S.backups[h])r+=`<tr><td>${h}</td><td>${f.name}</td><td>${(f.size/1024).toFixed(1)} KB</td></tr>`;
$("bk").innerHTML=r.includes("<td>")?r:r+'<tr><td colspan=3 style="color:var(--mut)">No backups yet</td></tr>';
const L=$("log"),atEnd=L.scrollTop+L.clientHeight>=L.scrollHeight-20;
L.innerHTML=S.logs.map(l=>`<div class="${l.lvl}"><span style="color:var(--mut)">${l.t}</span> <span class="src">[${l.src}]</span> ${l.msg.replace(/</g,"&lt;")}</div>`).join("");if(atEnd)L.scrollTop=L.scrollHeight}
async function tick(){try{S=await(await fetch("/api/state")).json();render()}catch(e){}}
$("fi").onchange=async e=>{const f=e.target.files[0];if(!f)return;$("drop").textContent="Uploading "+f.name+"...";
const j=await(await fetch("/api/upload?name="+encodeURIComponent(f.name),{method:"POST",body:f})).json();file=j.path;$("drop").textContent=f.name+" ("+(f.size/1024).toFixed(1)+" KB) ready";$("drop").classList.add("has")};
function sendFile(){const t=[...document.querySelectorAll(".tg:checked")].map(e=>e.value);if(!t.length)return alert("Select at least one server");post("/api/send",{path:file,targets:t})}
async function showFlows(){const f=await(await fetch("/api/flows")).json();$("flows").textContent=Object.entries(f).map(([s,l])=>`${s}: ${l.length} rules\n`+l.map(x=>"  "+x.replace(/duration=\S+ |table=\d+, |n_packets=\d+, n_bytes=\d+, |idle_age=\d+, /g,"")).join("\n")).join("\n\n")}
tick();setInterval(tick,1200);
</script></body></html>"""


def main():
    global net
    if os.geteuid() != 0:
        sys.exit("Run with sudo (Mininet needs root).")
    net = topo.build()
    net.start()
    log("system", "Mininet topology started", "ok")
    srv = ThreadingHTTPServer(("0.0.0.0", 8080), H)
    print("Dashboard running at http://localhost:8080  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs.values():
            if p.poll() is None:
                p.terminate()
        net.stop()


if __name__ == "__main__":
    main()