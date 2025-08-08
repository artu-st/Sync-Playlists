import os
import json
import time
import shutil
import xml.etree.ElementTree as ET
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Cargar configuración
def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)
config = load_config()

WATCH_DIRS = [p["playlist_dir"] for p in config["paths"]]
EXTS = {"m3u", "m3u8", "xml"}
INDEX_FILE = "output/playlist_index.json"
RECYCLE_BIN = config.get("recycle_bin", "recycle_bin")
LOG_FILE = "output/sync.log"
LOG_MAX_SIZE = 10 * 1024 * 1024
os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
os.makedirs(RECYCLE_BIN, exist_ok=True)

# Log utilities
def rotate_log():
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_SIZE:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            shutil.move(LOG_FILE, f"sync_{timestamp}.log")
    except Exception:
        pass

def log(message):
    rotate_log()
    entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(entry)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass

# Helpers
def get_playlist_name(path):
    return os.path.splitext(os.path.basename(path))[0]

def move_to_recycle(path):
    try:
        if os.path.exists(path):
            name = os.path.basename(path)
            ts = time.strftime("%Y%m%d-%H%M%S")
            shutil.move(path, os.path.join(RECYCLE_BIN, f"{name}.{ts}"))
    except Exception as e:
        log(f"Error recycle '{path}': {e}")

# Load or init index
def load_index():
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}
index = load_index()

def save_index():
    try:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except Exception as e:
        log(f"Error save index: {e}")

# Sync logic
def playlist_has_changed(name, paths_by_id):
    old = index.get(name)
    if old != paths_by_id:
        index[name] = paths_by_id
        save_index()
        return True
    return False

def parse_playlist(path):
    if not os.path.exists(path):
        return []
    ext = os.path.splitext(path)[1].lstrip('.').lower()
    if ext not in EXTS:
        return []
    try:
        if ext in ("m3u", "m3u8"):
            with open(path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            return lines
        if ext == "xml":
            tree = ET.parse(path)
            return [item.get("Path") for item in tree.findall('.//Item/Path')]
    except Exception as e:
        log(f"Error parse '{path}': {e}")
    return []

def convert_paths(paths, src, dst, to_m3u8=False):
    out = []
    for p in paths:
        try:
            rel = os.path.relpath(p, src)
            new = os.path.join(dst, rel)
            if to_m3u8:
                new = new.replace('/', '\\')
            else:
                new = new.replace('\\', '/')
            out.append(new)
        except:
            continue
    return out

def write_m3u(path, items):
    try:
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("#EXTM3U\r\n")
            for i in items:
                f.write(i + "\r\n")
    except Exception as e:
        log(f"Error write_m3u '{path}': {e}")

def write_m3u8(path, items):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for i in items:
                f.write(i + "\n")
    except Exception as e:
        log(f"Error write_m3u8 '{path}': {e}")

def write_xml(path, items):
    try:
        # Jellyfin-compatible XML
        root = ET.Element("Item")
        ET.SubElement(root, "Added").text = time.strftime("%m/%d/%Y %H:%M:%S")
        ET.SubElement(root, "LockData").text = "false"
        ET.SubElement(root, "LocalTitle").text = get_playlist_name(path)
        ET.SubElement(root, "RunningTime").text = "0"
        ET.SubElement(root, "Genres")
        ET.SubElement(root, "OwnerUserId").text = ""
        pi = ET.SubElement(root, "PlaylistItems")
        for i in items:
            it = ET.SubElement(pi, "PlaylistItem")
            ET.SubElement(it, "Path").text = i
        ET.SubElement(root, "Shares")
        ET.SubElement(root, "PlaylistMediaType").text = "Audio"
        decl = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
        s = ET.tostring(root, encoding="utf-8").decode()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(decl + s)
    except Exception as e:
        log(f"Error write_xml '{path}': {e}")

def sync_playlist(path):
    raw = parse_playlist(path)
    if not raw:
        return
    name = get_playlist_name(path)
    src = next((p for p in config["paths"] if path.startswith(p["playlist_dir"])), None)
    if not src:
        return
    conv = {}
    for p in config["paths"]:
        conv[p["id"]] = convert_paths(raw, src["base"], p["base"], to_m3u8=(p["type"]=="m3u8"))
    if not playlist_has_changed(name, conv):
        return
    for p in config["paths"]:
        out = os.path.join(p["playlist_dir"], name)
        if p["type"] == "xml":
            write_xml(out + "/playlist.xml", conv[p["id"]])
        else:
            fn = ".m3u8" if p["type"] == "m3u8" else ".m3u"
            write = write_m3u8 if p["type"]=="m3u8" else write_m3u
            write(out + fn, conv[p["id"]])
    log(f"Synced '{name}'")

def delete_playlist(name):
    if name not in index:
        return
    del index[name]
    save_index()
    for p in config["paths"]:
        if p["type"] == "xml":
            d = os.path.join(p["playlist_dir"], name)
            if os.path.isdir(d):
                for f in os.listdir(d): move_to_recycle(os.path.join(d, f))
                os.rmdir(d)
        else:
            ext = ".m3u8" if p["type"]=="m3u8" else ".m3u"
            move_to_recycle(os.path.join(p["playlist_dir"], name + ext))
    log(f"Deleted '{name}'")

class PlaylistHandler(FileSystemEventHandler):
    def on_any_event(self, e):
        if e.is_directory:
            return
        ext = os.path.splitext(e.src_path)[1].lstrip('.').lower()
        if ext not in EXTS:
            return
        if e.event_type in ("created", "modified"):
            sync_playlist(e.src_path)
        elif e.event_type == "deleted":
            delete_playlist(get_playlist_name(e.src_path))

# Initial sync and watch
if __name__ == "__main__":
    # initial
    for p in config["paths"]:
        d = p["playlist_dir"]
        if os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    path = os.path.join(root, f)
                    ext = os.path.splitext(path)[1].lstrip('.').lower()
                    if ext in EXTS:
                        sync_playlist(path)
    # observer
    obs = Observer()
    h = PlaylistHandler()
    for d in WATCH_DIRS:
        if os.path.exists(d): obs.schedule(h, d, recursive=True)
    obs.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()
