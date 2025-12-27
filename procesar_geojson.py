import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET
import geojson
from datetime import datetime, timezone
import pytz

# Leer la URL base desde el config.json
CONFIG_FILE = "config.json"
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"❌ Error: Archivo de configuración '{CONFIG_FILE}' not encontrado.")
    config = {"url_tar": "https://opendata.aemet.es/opendata/api/avisos/capa/geojson?api_key=YOUR_API_KEY"}

API_URL = config["url_tar"]
TAR_FILE_PATH = "datos/avisos.tar"
EXTRACT_PATH = "datos/geojson_temp"
SALIDA_GEOJSON = "avisos_espana.geojson"

# Prioridades para el orden de dibujado (Rojo encima de todo)
PRIORIDAD_NIVELES = {
    "rojo": 3,
    "naranja": 2,
    "amarillo": 1
}

colores = {
    "amarillo": "#f3f702",
    "naranja": "#FF7F00",
    "rojo": "#FF0000"
}

EMOJI_MAP = {
    "vientos": "🌬️", "lluvia": "🌧️", "nieve": "❄️", "tormentas": "⛈️",
    "costeros": "🌊", "temperaturas": "🌡️", "niebla": "🌫️", "aludes": "🏔️", "otro": "⚠️",
}

def get_type_and_emoji(event_text):
    event_text_lower = event_text.lower()
    for keyword, emoji in EMOJI_MAP.items():
        if keyword in event_text_lower:
            return event_text, emoji
    return event_text, EMOJI_MAP.get("otro", "❓")

def parse_iso_datetime(date_str):
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(pytz.timezone('Europe/Madrid'))
    except Exception:
        return None

def obtener_url_datos_desde_api():
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        datos = response.json()
        return datos.get("datos")
    except requests.RequestException as e:
        print(f"❌ Error al obtener la URL de datos: {e}")
        return None

def download_tar(url, download_path='avisos.tar'):
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(download_path, 'wb') as f:
            f.write(response.content)
        print("Archivo TAR descargado correctamente.")
    except Exception as e:
        print(f"Error al descargar el archivo TAR: {e}")

def extract_and_process_tar(tar_path='avisos.tar'):
    try:
        if not os.path.exists('datos'): os.makedirs('datos')
        with tarfile.open(tar_path, 'r:*') as tar:
            tar.extractall(path='datos')
        
        all_features = []
        for file_name in os.listdir('datos'):
            if file_name.endswith('.xml'):
                file_path = os.path.join('datos', file_name)
                features = process_xml_to_geojson(file_path)
                all_features.extend(features)

        # --- ORDENACIÓN POR GRAVEDAD ---
        # Ordenamos la lista para que los niveles más altos (rojo) vayan al FINAL de la lista
        # Leaflet dibuja los últimos elementos encima de los primeros.
        all_features.sort(key=lambda x: PRIORIDAD_NIVELES.get(x["properties"].get("parameter", "").lower(), 0))

        geojson_data = {
            "type": "FeatureCollection",
            "features": all_features
        }
        with open(SALIDA_GEOJSON, 'w', encoding='utf-8') as geojson_file:
            json.dump(geojson_data, geojson_file, indent=4)
        print(f"✅ GeoJSON guardado con {len(all_features)} avisos ordenados por gravedad.")
    except Exception as e:
        print(f"Error al procesar el archivo TAR: {e}")

def process_xml_to_geojson(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        namespaces = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
        areas = root.findall(".//info/area", namespaces)
        geojson_features = []
        now = datetime.now(pytz.utc).astimezone(pytz.timezone('Europe/Madrid'))

        for area in areas:
            polygon = area.find("polygon", namespaces)
            if polygon is not None:
                coordinates = polygon.text.strip()
                info = root.find(".//info", namespaces)
                onset_dt = parse_iso_datetime(info.findtext("onset", default="", namespaces=namespaces))
                expires_dt = parse_iso_datetime(info.findtext("expires", default="", namespaces=namespaces))

                if onset_dt and expires_dt and onset_dt <= now <= expires_dt:
                    parametros = info.findall("parameter", namespaces)
                    nivel_textual = next((p.findtext("value", namespaces=namespaces).lower() for p in parametros if "nivel" in p.findtext("valueName", namespaces=namespaces).lower()), None)

                    if nivel_textual in colores:
                        umap_options = {
                            "color": "#FFFFFF", "weight": 1, "opacity": 0.8,
                            "fillColor": colores[nivel_textual], "fillOpacity": 0.7,
                            "interactive": True
                        }
                        
                        feature = {
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": [parse_coordinates(coordinates)]},
                            "properties": {
                                "parameter": nivel_textual,
                                "_umap_options": umap_options,
                                "popup_html": generate_popup_html(info, area, nivel_textual, onset_dt, expires_dt)
                            }
                        }
                        geojson_features.append(feature)
        return geojson_features
    except Exception: return []

def generate_popup_html(info, area, nivel_textual, onset_dt, expires_dt):
    namespaces = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
    event_display, event_emoji = get_type_and_emoji(info.findtext("event", default="Otro", namespaces=namespaces))
    
    return (
        f"<b>{info.findtext('headline', namespaces=namespaces)}</b><br>"
        f"<b>Àrea:</b> {area.findtext('areaDesc', namespaces=namespaces)}<br>"
        f"<b>Nivell:</b> <span style='color:{colores.get(nivel_textual, '#000')}'>{nivel_textual.capitalize()}</span><br>"
        f"<b>Tipus:</b> {event_display} {event_emoji}<br>"
        f"<b>Inici:</b> {onset_dt.strftime('%d/%m/%Y %H:%M')}<br>"
        f"<b>Fi:</b> {expires_dt.strftime('%d/%m/%Y %H:%M')}"
    )

def parse_coordinates(coordinates_str):
    return [[float(c.split(',')[1]), float(c.split(',')[0])] for c in coordinates_str.split()]

download_url = obtener_url_datos_desde_api()
if download_url:
    download_tar(download_url, 'avisos.tar')
    extract_and_process_tar('avisos.tar')
