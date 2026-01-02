import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURACIÓN ---
CONFIG_FILE = "config.json"
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except:
    # IMPORTANTE: Reemplaza TU_API_KEY si no usas config.json
    config = {"url_tar": "https://opendata.aemet.es/opendata/api/avisos_cap/ultimoelaborado/area/esp?api_key=TU_API_KEY"}

API_URL = config["url_tar"]
SALIDA_GEOJSON = "avisos_espana.geojson"

PRIORIDAD_NIVELES = {"rojo": 3, "naranja": 2, "amarillo": 1}
colores = {"amarillo": "#f3f702", "naranja": "#FF7F00", "rojo": "#FF0000"}
EMOJI_MAP = {"vientos": "🌬️", "lluvia": "🌧️", "nieve": "❄️", "tormentas": "⛈️", "costeros": "🌊", "temperaturas": "🌡️", "niebla": "🌫️", "aludes": "🏔️", "otro": "⚠️"}

# --- FUNCIONES DE APOYO ---

def get_session():
    """Crea una sesión con reintentos y User-Agent para evitar bloqueos."""
    session = requests.Session()
    retry_strategy = Retry(
        total=4,
        backoff_factor=2, # Espera 2, 4, 8 segundos entre reintentos
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    return session

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

def parse_coordinates(s):
    return [[float(c.split(',')[1]), float(c.split(',')[0])] for c in s.strip().split()]

def process_xml_to_geojson(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
        features = []
        madrid_tz = pytz.timezone('Europe/Madrid')
        hoy = datetime.now(madrid_tz).date()

        for info in root.findall(".//info", ns):
            if info.findtext("language", "", ns) != "es-ES": continue

            onset_dt = parse_iso_datetime(info.findtext("onset", "", ns))
            expires_dt = parse_iso_datetime(info.findtext("expires", "", ns))
            if not onset_dt: continue

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
                        event_display, event_emoji = get_type_and_emoji(info.findtext("event", "", ns))
                        
                        popup_html = (
                            f"<h3>{event_emoji} {event_display}</h3>"
                            f"<p><b>Titular:</b> {info.findtext('headline', '', ns)}</p>"
                            f"<p><b>Área:</b> {area.findtext('areaDesc', '', ns)}</p>"
                            f"<p><b>Nivel:</b> <span style='color:{colores[nivel]}; font-weight:bold;'>{nivel.upper()}</span></p>"
                            f"<hr>"
                            f"<p><b>Descripción:</b> {info.findtext('description', '', ns)}</p>"
                            f"<p><b>Instrucciones:</b> {info.findtext('instruction', '', ns)}</p>"
                            f"<p><b>Inicio:</b> {onset_dt.strftime('%d/%m/%Y %H:%M')}</p>"
                            f"<p><b>Fin:</b> {expires_dt.strftime('%d/%m/%Y %H:%M')}</p>"
                            f"<p><a href='{info.findtext('web', 'https://www.aemet.es', ns)}' target='_blank' style='color:#0078A8;'>Ver en AEMET</a></p>"
                        )

                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": [parse_coordinates(polygon.text)]},
                            "properties": {
                                "dia": diferencia,
                                "priority": PRIORIDAD_NIVELES.get(nivel, 0),
                                "popup_html": popup_html,
                                "fillColor": colores[nivel]
                            }
                        })
        return features
    except Exception as e:
        print(f"Error procesando XML {file_path}: {e}")
        return []

# --- LÓGICA PRINCIPAL ---

def ejecutar():
    session = get_session()
    
    try:
        print("Solicitando URL de descarga a AEMET...")
        res = session.get(API_URL, timeout=30)
        res.raise_for_status()
        url_tar = res.json().get("datos")
        
        if not url_tar:
            print("No se encontró la URL de los datos en la respuesta.")
            return

        print("Descargando archivo TAR...")
        r = session.get(url_tar, timeout=60)
        r.raise_for_status()
        
        with open('avisos.tar', 'wb') as f: 
            f.write(r.content)
            
        if os.path.exists('datos'): 
            shutil.rmtree('datos')
        os.makedirs('datos')
        
        with tarfile.open('avisos.tar', 'r:*') as tar:
            tar.extractall(path='datos')
            
        todas = []
        for f in os.listdir('datos'):
            if f.endswith('.xml'): 
                todas.extend(process_xml_to_geojson(os.path.join('datos', f)))
        
        # Guardar resultado final
        with open(SALIDA_GEOJSON, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": todas}, f, indent=4)
            
        print(f"Éxito: {len(todas)} avisos procesados en {SALIDA_GEOJSON}")

    except requests.exceptions.HTTPError as e:
        print(f"Error HTTP (posible bloqueo): {e}")
    except Exception as e:
        print(f"Error inesperado: {e}")

if __name__ == "__main__":
    ejecutar()