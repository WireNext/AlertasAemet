import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET
import geojson
from datetime import datetime, timezone
import pytz

# Configuración
CONFIG_FILE = "config.json"
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {"url_tar": "https://opendata.aemet.es/opendata/api/avisos_cap/ultimoelaborado/area/esp?api_key=TU_API_KEY"}

API_URL = config["url_tar"]
SALIDA_GEOJSON = "avisos_espana.geojson"

PRIORIDAD_NIVELES = {"rojo": 3, "naranja": 2, "amarillo": 1}
colores = {"amarillo": "#f3f702", "naranja": "#FF7F00", "rojo": "#FF0000"}
EMOJI_MAP = {"vientos": "🌬️", "lluvia": "🌧️", "nieve": "❄️", "tormentas": "⛈️", "costeros": "🌊", "temperaturas": "🌡️", "niebla": "🌫️", "aludes": "🏔️", "otro": "⚠️"}

def get_type_and_emoji(event_text):
    event_text_lower = event_text.lower()
    for keyword, emoji in EMOJI_MAP.items():
        if keyword in event_text_lower:
            return event_text, emoji
    return event_text, EMOJI_MAP.get("otro", "❓")

def parse_iso_datetime(date_str):
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(pytz.timezone('Europe/Madrid'))
    except Exception: return None

def obtener_url_datos_desde_api():
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        return response.json().get("datos")
    except: return None

def extract_and_process_tar(tar_path='avisos.tar'):
    if os.path.exists('datos'): shutil.rmtree('datos')
    os.makedirs('datos')
    try:
        with tarfile.open(tar_path, 'r:*') as tar:
            tar.extractall(path='datos')
        all_features = []
        for file_name in os.listdir('datos'):
            if file_name.endswith('.xml'):
                all_features.extend(process_xml_to_geojson(os.path.join('datos', file_name)))
        all_features.sort(key=lambda x: PRIORIDAD_NIVELES.get(x["properties"].get("parameter", "").lower(), 0))
        with open(SALIDA_GEOJSON, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": all_features}, f, indent=4)
    except Exception as e: print(f"Error: {e}")

def process_xml_to_geojson(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
        geojson_features = []
        now = datetime.now(pytz.utc).astimezone(pytz.timezone('Europe/Madrid'))
        for area in root.findall(".//info/area", ns):
            polygon = area.find("polygon", ns)
            if polygon is not None:
                info = root.find(".//info", ns)
                onset_dt = parse_iso_datetime(info.findtext("onset", "", ns))
                expires_dt = parse_iso_datetime(info.findtext("expires", "", ns))
                if onset_dt and expires_dt and onset_dt <= now <= expires_dt:
                    parametros = info.findall("parameter", ns)
                    nivel = next((p.findtext("value", "", ns).lower() for p in parametros if "nivel" in p.findtext("valueName", "", ns).lower()), "verde")
                    if nivel in colores:
                        properties = {
                            "parameter": nivel,
                            "priority": PRIORIDAD_NIVELES.get(nivel, 0),
                            "popup_html": generate_popup_html(info, area, nivel, onset_dt, expires_dt),
                            "_umap_options": {"fillColor": colores[nivel], "color": "#FFFFFF", "weight": 1, "fillOpacity": 0.8}
                        }
                        geojson_features.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [parse_coordinates(polygon.text)]}, "properties": properties})
        return geojson_features
    except: return []

def generate_popup_html(info, area, nivel, onset_dt, expires_dt):
    ns = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
    event, emoji = get_type_and_emoji(info.findtext("event", "Altre", ns))
    # Mapeo de nombres de nivel al valenciano
    traduccion_nivel = {"rojo": "Roig", "naranja": "Taronja", "amarillo": "Groc"}
    nivel_val = traduccion_nivel.get(nivel, nivel.capitalize())

    return (
        f"<b>{info.findtext('headline', '', ns)}</b><br>"
        f"<b>Àrea:</b> {area.findtext('areaDesc', '', ns)}<br>"
        f"<b>Nivell d'alerta:</b> <span style='color:{colores.get(nivel, '#000')}'>{nivel_val}</span><br>"
        f"<b>Tipus:</b> {event} {emoji}<br>"
        f"<b>Descripció:</b> {info.findtext('description', '', ns)}<br>"
        f"<b>Instruccions:</b> {info.findtext('instruction', '', ns)}<br>"
        f"<b>Data d'inici:</b> {onset_dt.strftime('%d/%m/%Y %H:%M')}<br>"
        f"<b>Data de fi:</b> {expires_dt.strftime('%d/%m/%Y %H:%M')}<br>"
        f"<b>Més informació:</b> <a href='{info.findtext('web', '', ns)}' target='_blank'>AEMET</a>"
    )

def parse_coordinates(s):
    return [[float(c.split(',')[1]), float(c.split(',')[0])] for c in s.strip().split()]

url = obtener_url_datos_desde_api()
if url:
    r = requests.get(url)
    with open('avisos.tar', 'wb') as f: f.write(r.content)
    extract_and_process_tar('avisos.tar')
