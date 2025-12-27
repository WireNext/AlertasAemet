import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import pytz

# Configuración
CONFIG_FILE = "config.json"
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except:
    config = {"url_tar": "https://opendata.aemet.es/opendata/api/avisos_cap/ultimoelaborado/area/esp?api_key=TU_API_KEY"}

API_URL = config["url_tar"]
SALIDA_GEOJSON = "avisos_espana.geojson"

# Prioridades y Colores Sólidos
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
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.astimezone(pytz.timezone('Europe/Madrid'))
    except: return None

def process_xml_to_geojson(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
        features = []

        for info in root.findall(".//info", ns):
            # SOLO ESPAÑOL
            if info.findtext("language", "", ns) != "es-ES":
                continue

            headline = info.findtext("headline", "", ns)
            description = info.findtext("description", "", ns)
            instruction = info.findtext("instruction", "Sin instrucciones específicas", ns)
            event = info.findtext("event", "", ns)
            area_desc = info.find(".//area/areaDesc", ns).text
            web = info.findtext("web", "https://www.aemet.es", ns)
            onset_dt = parse_iso_datetime(info.findtext("onset", "", ns))
            expires_dt = parse_iso_datetime(info.findtext("expires", "", ns))

            nivel = "verde"
            for p in info.findall("parameter", ns):
                if "nivel" in p.findtext("valueName", "", ns).lower():
                    nivel = p.findtext("value", "", ns).lower()

            if nivel in colores:
                for area in info.findall("area", ns):
                    polygon = area.find("polygon", ns)
                    if polygon is not None:
                        event_display, event_emoji = get_type_and_emoji(event)
                        
                        # Popup construido totalmente en español
                        popup_html = (
                            f"<b>{headline}</b><br>"
                            f"<b>Área:</b> {area_desc}<br>"
                            f"<b>Nivel de alerta:</b> <span style='color:{colores[nivel]}'>{nivel.capitalize()}</span><br>"
                            f"<b>Tipo:</b> {event_display} {event_emoji}<br>"
                            f"<b>Descripción:</b> {description}<br>"
                            f"<b>Instrucciones:</b> {instruction}<br>"
                            f"<b>Inicio:</b> {onset_dt.strftime('%d/%m/%Y %H:%M')}<br>"
                            f"<b>Fin:</b> {expires_dt.strftime('%d/%m/%Y %H:%M')}<br>"
                            f"<b>Más información:</b> <a href='{web}' target='_blank'>AEMET</a>"
                        )

                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": [parse_coordinates(polygon.text)]},
                            "properties": {
                                "parameter": nivel,
                                "priority": PRIORIDAD_NIVELES.get(nivel, 0),
                                "popup_html": popup_html,
                                "_umap_options": {
                                    "fillColor": colores[nivel], 
                                    "color": "#000000", 
                                    "weight": 1, 
                                    "fillOpacity": 1.0 # COLOR SÓLIDO SIN TRANSPARENCIA
                                }
                            }
                        })
        return features
    except: return []

def parse_coordinates(s):
    return [[float(c.split(',')[1]), float(c.split(',')[0])] for c in s.strip().split()]

def ejecutar():
    res = requests.get(API_URL)
    url_tar = res.json().get("datos")
    if url_tar:
        r = requests.get(url_tar)
        with open('avisos.tar', 'wb') as f: f.write(r.content)
        if os.path.exists('datos'): shutil.rmtree('datos')
        os.makedirs('datos')
        with tarfile.open('avisos.tar', 'r:*') as tar:
            tar.extractall(path='datos')
        todas = []
        for f in os.listdir('datos'):
            if f.endswith('.xml'): todas.extend(process_xml_to_geojson(os.path.join('datos', f)))
        todas.sort(key=lambda x: x["properties"]["priority"])
        with open(SALIDA_GEOJSON, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": todas}, f, indent=4)

ejecutar()
