import os
import json
import time
import shutil
import xml.etree.ElementTree as ET
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ===============================
# Cargar configuración
# ===============================

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

WATCH_DIRS = [p["playlist_dir"] for p in config["paths"]]
INDEX_FILE = "output/playlist_index.json"
RECYCLE_BIN = config["recycle_bin"]
LOG_FILE = "output/sync.log"
LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 MB

os.makedirs(RECYCLE_BIN, exist_ok=True)

# ===============================
# Logging y utilidades básicas
# ===============================

def rotate_log():
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_SIZE:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.move(LOG_FILE, f"sync_{timestamp}.log")

def log(message):
    rotate_log()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

def get_playlist_name(path):
    return os.path.splitext(os.path.basename(path))[0]

def move_to_recycle(path):
    if os.path.exists(path):
        name = os.path.basename(path)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.move(path, os.path.join(RECYCLE_BIN, f"{name}.{timestamp}"))

# ===============================
# Cargar índice de sincronización
# ===============================

if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)
else:
    index = {}

def playlist_has_changed(name, paths):
    if index.get(name) != paths:
        index[name] = paths
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
        return True
    return False

# ===============================
# Conversión de rutas y formatos
# ===============================

def convert_paths(paths, src_base, dst_base, to_windows=False):
    result = []
    for p in paths:
        rel = os.path.relpath(p, src_base)
        new = os.path.join(dst_base, rel)
        result.append(new.replace("/", "\\") if to_windows else new.replace("\\", "/"))
    return result

def parse_playlist(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in [".m3u", ".m3u8"]:
        with open(path, "r", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if ext == ".xml":
        tree = ET.parse(path)
        return [item.get("Path") for item in tree.getroot().findall("Item")]
    return []

def write_m3u(path, items):
    try:
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("#EXTM3U\r\n")
            for item in items:
                f.write(item + "\r\n")
    except PermissionError as e:
        log(f"❌ Error de permiso al escribir '{path}': {e}")
    

def write_m3u8(path, items):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in items:
                f.write(item + "\n")
    except PermissionError as e:
        log(f"❌ Error de permiso al escribir '{path}': {e}")

def write_xml(path, items):
    root = ET.Element("Playlist")
    for item in items:
        ET.SubElement(root, "Item", {"Path": item})
    tree = ET.ElementTree(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)

# ===============================
# Sincronización de listas
# ===============================

def sync_playlist(source_path):
    name = get_playlist_name(source_path)

    # Detectar desde qué entrada viene
    src_entry = next((p for p in config["paths"] if source_path.startswith(p["playlist_dir"])), None)
    if not src_entry:
        return

    # Obtener rutas relativas desde origen a los destinos
    base_paths = {}
    raw_paths = parse_playlist(source_path)
    for entry in config["paths"]:
        key = entry["type"]
        if key == "windows":
            base_paths[key] = convert_paths(raw_paths, src_entry["base"], entry["base"], to_windows=True)
        else:
            base_paths[key] = convert_paths(raw_paths, src_entry["base"], entry["base"])

    if not playlist_has_changed(name, base_paths):
        log(f"⏩ Sin cambios en '{name}'")
        return

    # Reescribir la lista de reproducción en cada destino
    for entry in config["paths"]:
        out_path = os.path.join(entry["playlist_dir"], f"{name}")
        if entry["type"] == "windows":
            write_m3u8(out_path + ".m3u8", base_paths["windows"])
        elif entry["type"] == "synology":
            write_m3u(out_path + ".m3u", base_paths["synology"])
        elif entry["type"] == "jellyfin":
            write_xml(os.path.join(out_path, "playlist.xml"), base_paths["jellyfin"])

    log(f"✅ Playlist '{name}' sincronizada")

# ===============================
# Eliminación de listas
# ===============================

def delete_playlist(name):
    if name in index:
        del index[name]
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)

    for entry in config["paths"]:
        pdir = entry["playlist_dir"]
        ext = ".m3u8" if entry["type"] == "windows" else ".m3u"

        if entry["type"] == "jellyfin":
            folder = os.path.join(pdir, name)
            if os.path.exists(folder):
                for file in os.listdir(folder):
                    move_to_recycle(os.path.join(folder, file))
                os.rmdir(folder)
        else:
            path = os.path.join(pdir, f"{name}{ext}")
            move_to_recycle(path)

    log(f"🗑️ Playlist '{name}' eliminada")

# ===============================
# Observador de eventos del sistema
# ===============================

class PlaylistHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            sync_playlist(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            sync_playlist(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            delete_playlist(get_playlist_name(event.src_path))


# ===============================
# Sincronización inicial completa
# ===============================

def initial_sync():
    log("🔍 Escaneando listas existentes antes de iniciar monitoreo...")

    playlist_files = {}

    # Recolectar todas las playlists por nombre base
    for entry in config["paths"]:
        pdir = entry["playlist_dir"]
        ptype = entry["type"]
        ext = ".xml" if ptype == "jellyfin" else (".m3u8" if ptype == "windows" else ".m3u")

        if not os.path.exists(pdir):
            continue

        for item in os.listdir(pdir):
            full_path = os.path.join(pdir, item)
            if ptype == "jellyfin" and os.path.isdir(full_path):
                xml_path = os.path.join(full_path, "playlist.xml")
                if os.path.exists(xml_path):
                    name = os.path.basename(full_path)
                    playlist_files.setdefault(name, []).append((xml_path, os.path.getmtime(xml_path)))
            elif os.path.isfile(full_path) and item.lower().endswith(ext):
                name = os.path.splitext(item)[0]
                playlist_files.setdefault(name, []).append((full_path, os.path.getmtime(full_path)))

    # Para cada playlist, determinar la más reciente y sincronizar
    for name, files in playlist_files.items():
        files.sort(key=lambda x: x[1], reverse=True)  # Ordenar por fecha desc (más reciente primero)
        source_file = files[0][0]
        log(f"🕓 Playlist más reciente '{name}': {source_file}")
        sync_playlist(source_file)


# ===============================
# Monitorización en tiempo real
# ===============================

if __name__ == "__main__":
    log("🔁 Iniciando sincronización de playlists")
    initial_sync()
    observer = Observer()
    handler = PlaylistHandler()
    for path in WATCH_DIRS:
        if os.path.exists(path):
            observer.schedule(handler, path, recursive=True)
            log(f"👁️ Observando: {path}")
        else:
            log(f"❌ Ruta no encontrada, se omite: {path}")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()