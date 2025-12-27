import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
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

PRIORIDAD_NIVELES = {"rojo": 3, "naranja": 2, "amarillo": 1}
colores = {"amarillo": "#f3f702", "naranja": "#FF7F00", "rojo": "#FF0000"}

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
        madrid_tz = pytz.timezone('Europe/Madrid')
        hoy = datetime.now(madrid_tz).date()

        for info in root.findall(".//info", ns):
            if info.findtext("language", "", ns) != "es-ES":
                continue

            onset_dt = parse_iso_datetime(info.findtext("onset", "", ns))
            expires_dt = parse_iso_datetime(info.findtext("expires", "", ns))
            if not onset_dt: continue

            # Determinar a qué día pertenece (0=hoy, 1=mañana, 2=pasado)
            diferencia = (onset_dt.date() - hoy).days
            if diferencia < 0 or diferencia > 2: continue 

            nivel = "verde"
            for p in info.findall("parameter", ns):
                if "nivel" in p.findtext("valueName", "", ns).lower():
                    nivel = p.findtext("value", "", ns).lower()

            if nivel in colores:
                for area in info.findall("area", ns):
                    polygon = area.find("polygon", ns)
                    if polygon is not None:
                        popup_html = (
                            f"<b>{info.findtext('headline', '', ns)}</b><br>"
                            f"<b>Área:</b> {area.findtext('areaDesc', '', ns)}<br>"
                            f"<b>Inicio:</b> {onset_dt.strftime('%d/%m/%Y %H:%M')}<br>"
                            f"<b>Fin:</b> {expires_dt.strftime('%d/%m/%Y %H:%M')}<br>"
                            f"<b>Instrucciones:</b> {info.findtext('instruction', 'Sin instrucciones', ns)}"
                        )

                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": [parse_coordinates(polygon.text)]},
                            "properties": {
                                "dia": diferencia, # 0, 1 o 2
                                "parameter": nivel,
                                "priority": PRIORIDAD_NIVELES.get(nivel, 0),
                                "popup_html": popup_html,
                                "fillColor": colores[nivel]
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
        with open(SALIDA_GEOJSON, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": todas}, f, indent=4)

ejecutar()
