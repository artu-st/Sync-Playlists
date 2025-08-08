# Sync Playlists

## Descripción

Sync Playlists es una herramienta de sincronización bidireccional de listas de reproducción musicales entre diferentes sistemas y formatos. Está diseñada para mantener actualizadas las listas de reproducción que se almacenan en múltiples ubicaciones y formatos, como Windows (M3U8), Synology (M3U) y Jellyfin (XML).

El sistema detecta cambios en cualquiera de las carpetas monitorizadas y replica esos cambios automáticamente en las demás ubicaciones, asegurando que todas las listas estén siempre sincronizadas y actualizadas.

## Funcionalidades

- Monitorización en tiempo real de cambios en las carpetas de listas de reproducción configuradas.
- Soporte para múltiples tipos de sistemas:
  - Windows: Listas en formato `.m3u8`
  - Synology: Listas en formato `.m3u`
  - Jellyfin: Listas en formato `.xml`
- Sincronización bidireccional: cambios realizados en cualquiera de las ubicaciones se reflejan en las demás.
- Detección y sincronización solo si la lista ha cambiado realmente.
- Conversión automática de rutas de archivos entre los diferentes sistemas y formatos.
- Manejo de eliminaciones: si se borra una lista en alguna ubicación, se elimina también en las demás.
- Papelera de reciclaje: las listas eliminadas se mueven a una carpeta configurable para recuperación.
- Registro (log) de operaciones y errores, con rotación automática de archivos de log para evitar archivos muy grandes.
- Control de errores para rutas inexistentes o accesos fallidos, con reporte en el log.
- Configuración flexible a través de un archivo JSON que permite definir múltiples rutas de origen y destino con sus tipos correspondientes.

## Requisitos

- Python 3.7 o superior
- Paquete `watchdog` (se instala con pip)

## Instalación

1. **Instalar Python**

   Descarga e instala Python 3.7 o superior desde [python.org](https://www.python.org/downloads/).

2. **Descargar o clonar el repositorio**

   ```bash
   git clone https://tu-repo-url.git
   cd nombre-del-repositorio


## Configuración

El archivo `config.json` debe contener la configuración de rutas y tipos. 

paths: Lista de ubicaciones donde se almacenan y sincronizan las listas de reproducción.
type: Define el tipo de sistema y formato:
    "windows": usa listas en formato .m3u8.
    "synology": usa listas en formato .m3u.
    "jellyfin": usa listas en formato .xml.
base: Ruta base donde están los archivos musicales. Se usa para calcular rutas relativas dentro de las listas.
playlist_dir: Carpeta donde se guardan y monitorizan las listas de reproducción para ese sistema.
recycle_bin: Carpeta donde se moverán las listas eliminadas para recuperación.

por ejemplo:

```json
{
  "recycle_bin": "D:/Playlists_Recicladas",
  "paths": [
    {
      "type": "windows",
      "base": "D:/Music",
      "playlist_dir": "D:/Music/Playlists"
    },
    {
      "type": "synology",
      "base": "/volume1/music",
      "playlist_dir": "/volume1/music/Playlists"
    },
    {
      "type": "jellyfin",
      "base": "/mnt/media/music",
      "playlist_dir": "D:/Jellyfin/Config/playlists"
    }
  ] 
}