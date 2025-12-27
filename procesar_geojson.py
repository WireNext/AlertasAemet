import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import pytz

# Configuració
CONFIG_FILE = "config.json"
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except:
    config = {"url_tar": "https://opendata.aemet.es/opendata/api/avisos_cap/ultimoelaborado/area/esp?api_key=TU_API_KEY"}

API_URL = config["url_tar"]
SALIDA_GEOJSON = "avisos_espana.geojson"

# Diccionari de traducció manual per a conceptes meteorològics
TRADUCCIONS = {
    "Severe rain warning": "Avís de pluges intenses",
    "Rain warning": "Avís de pluges",
    "Wind warning": "Avís de vent",
    "Coastal events": "Fenòmens costaners",
    "Snowfall": "Nevades",
    "Thunderstorms": "Tormentes",
    "Maximum temperature": "Temperatura màxima",
    "Minimum temperature": "Temperatura mínima",
    "Fog": "Boira",
    "Twelve-hours accumulated precipitation": "Precipitació acumulada en 12 hores",
    "One-hour accumulated precipitation": "Precipitació acumulada en 1 hora",
    "level": "nivell",
    "yellow": "groc",
    "orange": "taronja",
    "red": "roig",
    "Be prepared": "Estiga preparat",
    "Take precautions": "Prenga precaucions",
    "Keep up to date": "Mantinga's informat",
    "Severe damages may occur": "Es poden produir danys greus",
    "especially to those vulnerable": "especialment a persones vulnerables",
    "Litoral norte": "Litoral nord",
    "Litoral sur": "Litoral sud",
    "Interior norte": "Interior nord",
    "Interior sur": "Interior sud",
}

def traduir_text(text):
    if not text: return ""
    text_traduit = text
    for original, traduccio in TRADUCCIONS.items():
        text_traduit = text_traduit.replace(original, traduccio)
    # Traduccions ràpides de frases de l'AEMET castellà -> valencià
    text_traduit = text_traduit.replace("Aviso de", "Avís de").replace("nivel", "nivell")
    return text_traduit

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

        # Intentem buscar primer el bloc en castellà, si no existeix, agafem el que hi haja i el traduïm
        infos = root.findall(".//info", ns)
        info_valida = None
        for i in infos:
            if i.findtext("language", "", ns) == "es-ES":
                info_valida = i
                break
        if not info_valida and infos: info_valida = infos[0]

        if info_valida is not None:
            # Traducció activa de dades
            headline = traduir_text(info_valida.findtext("headline", "", ns))
            description = traduir_text(info_valida.findtext("description", "", ns))
            instruction = traduir_text(info_valida.findtext("instruction", "", ns))
            event = traduir_text(info_valida.findtext("event", "", ns))
            area_desc_raw = info_valida.find(".//area/areaDesc", ns).text if info_valida.find(".//area/areaDesc", ns) is not None else ""
            area_desc = traduir_text(area_desc_raw)
            
            web = info_valida.findtext("web", "https://www.aemet.es", ns)
            onset_dt = parse_iso_datetime(info_valida.findtext("onset", "", ns))
            expires_dt = parse_iso_datetime(info_valida.findtext("expires", "", ns))

            nivel = "verde"
            for p in info_valida.findall("parameter", ns):
                if "nivel" in p.findtext("valueName", "", ns).lower():
                    nivel = p.findtext("value", "", ns).lower()

            if nivel in colores:
                for area in info_valida.findall("area", ns):
                    polygon = area.find("polygon", ns)
                    if polygon is not None:
                        event_display, event_emoji = get_type_and_emoji(event)
                        
                        nivell_noms = {"rojo": "Roig", "naranja": "Taronja", "amarillo": "Groc"}
                        
                        popup_html = (
                            f"<b>{headline}</b><br>"
                            f"<b>Àrea:</b> {area_desc}<br>"
                            f"<b>Nivell d'alerta:</b> <span style='color:{colores[nivel]}'>{nivell_noms.get(nivel, nivel)}</span><br>"
                            f"<b>Tipus:</b> {event_display} {event_emoji}<br>"
                            f"<b>Descripció:</b> {description}<br>"
                            f"<b>Instruccions:</b> {instruction}<br>"
                            f"<b>Data d'inici:</b> {onset_dt.strftime('%d/%m/%Y %H:%M') if onset_dt else '--'}<br>"
                            f"<b>Data de fi:</b> {expires_dt.strftime('%d/%m/%Y %H:%M') if expires_dt else '--'}<br>"
                            f"<b>Més informació:</b> <a href='{web}' target='_blank'>AEMET</a>"
                        )

                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": [parse_coordinates(polygon.text)]},
                            "properties": {
                                "parameter": nivel,
                                "priority": PRIORIDAD_NIVELES.get(nivel, 0),
                                "popup_html": popup_html,
                                "_umap_options": {"fillColor": colores[nivel], "color": "#FFFFFF", "weight": 1, "fillOpacity": 0.7}
                            }
                        })
        return features
    except Exception as e:
        print(f"Error: {e}")
        return []

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
        todas_features = []
        for f in os.listdir('datos'):
            if f.endswith('.xml'):
                todas_features.extend(process_xml_to_geojson(os.path.join('datos', f)))
        todas_features.sort(key=lambda x: x["properties"]["priority"])
        with open(SALIDA_GEOJSON, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": todas_features}, f, indent=4)

ejecutar()
