import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET # Importamos el módulo para parsear XML
import geojson # Importamos el módulo para crear archivos GeoJSON
from datetime import datetime, timezone
import pytz


# Leer la URL base desde el config.json
CONFIG_FILE = "config.json"
# Asegúrate de que el archivo config.json exista o maneja la excepción.
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"❌ Error: Archivo de configuración '{CONFIG_FILE}' no encontrado.")
    # Usar valores predeterminados o salir
    config = {"url_tar": "https://opendata.aemet.es/opendata/api/avisos/capa/geojson?api_key=YOUR_API_KEY"}

API_URL = config["url_tar"] # Esta es la URL fija a la API de AEMET con la api_key
TAR_FILE_PATH = "datos/avisos.tar"
EXTRACT_PATH = "datos/geojson_temp"
SALIDA_GEOJSON = "avisos_espana.geojson"

# Mensajes de advertencia según nivel de alerta (en catalán, como el original)
WARNING_MESSAGES = {
    "Amarillo": "Vaja amb compte, mantinga's informat de les últimes previsions meteorològiques. Poden produir-se danys moderats a persones i propietats, especialment a persones vulnerables o en zones exposades.",
    "Naranja": "Estiga atent i mantinga's al dia amb les últimes previsions meteorològiques. Poden produir-se danys moderats a persones i propietats, especialment a persones vulnerables o en zones exposades.",
    "Rojo": "Prenga mesures de precaució, romanga alerta i actue segons els consells de les autoritats. Mantinga's al dia amb les últimes previsions meteorològiques. Viatge sol si el seu viatge és imprescindible. Poden produir-se danys extrems o catastròfics a persones i propietats, especialment a les persones vulnerables o en zones exposades."
}

# Diccionario de colores para los niveles de alerta
colores = {
    "amarillo": "#f3f702",
    "naranja": "#FF7F00",
    "rojo": "#FF0000"
}

# Nuevo: Diccionario para mapear tipos de evento (Tipus) a emojis
EMOJI_MAP = {
    "vientos": "🌬️",
    "lluvia": "🌧️",
    "nieve": "❄️",
    "tormentas": "⛈️",
    "costeros": "🌊", # Fenómenos Costeros
    "temperaturas": "🌡️", # Olas de calor/frío
    "niebla": "🌫️",
    "aludes": "🏔️",
    "otro": "⚠️",
}

def get_type_and_emoji(event_text):
    """
    Busca la palabra clave del tipo de evento en el texto y devuelve el emoji.
    """
    event_text_lower = event_text.lower()
    
    # Busca la primera palabra clave que coincida
    for keyword, emoji in EMOJI_MAP.items():
        if keyword in event_text_lower:
            return event_text, emoji
    
    # Si no encuentra coincidencia, devuelve el evento original y el emoji de "otro"
    return event_text, EMOJI_MAP.get("otro", "❓")


def parse_iso_datetime(date_str):
    try:
        # Convertimos la cadena ISO a objeto datetime con zona horaria incluida
        dt = datetime.fromisoformat(date_str)
        
        # Si la hora no tiene zona horaria, establecerla explícitamente como UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
            
        return dt.astimezone(pytz.timezone('Europe/Madrid')) # Convertimos a la hora de Madrid
    except Exception:
        return None

def obtener_url_datos_desde_api():
    """Obtiene la URL del archivo de datos desde la API de AEMET."""
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        datos = response.json()
        return datos.get("datos")
    except requests.RequestException as e:
        print(f"❌ Error al obtener la URL de datos: {e}")
        return None

# Función para descargar el archivo .tar
def download_tar(url, download_path='avisos.tar'):
    try:
        response = requests.get(url)
        response.raise_for_status() # Lanza un error si la descarga falla
        with open(download_path, 'wb') as f:
            f.write(response.content)
        print("Archivo TAR descargado correctamente.")
    except Exception as e:
        print(f"Error al descargar el archivo TAR: {e}")

def extract_and_process_tar(tar_path='avisos.tar'):
    try:
        # Extraer el contenido del archivo TAR
        with tarfile.open(tar_path, 'r:*') as tar:
            tar.extractall(path='datos') # Extrae los archivos en la carpeta 'datos'
        print("Archivos extraídos correctamente.")
        
        all_features = [] # Aquí acumulamos todos los avisos

        # Procesar cada archivo XML extraído
        for file_name in os.listdir('datos'):
            if file_name.endswith('.xml'):
                file_path = os.path.join('datos', file_name)
                features = process_xml_to_geojson(file_path) # ← ahora devuelve los features
                all_features.extend(features)

        # Leer el archivo GeoJSON existente si existe (lógica para combinar avisos filtrados no se usa aquí, solo se reescribe el archivo)
        
        # Guardar todos los features activos en un solo GeoJSON
        geojson_data = {
            "type": "FeatureCollection",
            "features": all_features # puede estar vacío
        }
        try:
            with open(SALIDA_GEOJSON, 'w', encoding='utf-8') as geojson_file:
                json.dump(geojson_data, geojson_file, indent=4)
            print(f"✅ GeoJSON guardado en {SALIDA_GEOJSON} con {len(all_features)} avisos activos.")
        except Exception as e:
            print(f"❌ Error al guardar el GeoJSON: {e}")
    except Exception as e:
        print(f"Error al extraer y procesar el archivo TAR: {e}")


def process_xml_to_geojson(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        namespaces = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
        areas = root.findall(".//info/area", namespaces)
        geojson_features = []
        # Asegurarse de que 'now' tiene una zona horaria para la comparación
        now = datetime.now(pytz.utc).astimezone(pytz.timezone('Europe/Madrid'))

        for area in areas:
            polygon = area.find("polygon", namespaces)
            if polygon is not None:
                coordinates = polygon.text.strip()
                info = root.find(".//info", namespaces)

                # Obtener fechas
                onset_text = info.findtext("onset", default="", namespaces=namespaces)
                expires_text = info.findtext("expires", default="", namespaces=namespaces)
                
                # Convertir a objetos datetime con zona horaria de Madrid
                onset_dt = parse_iso_datetime(onset_text)
                expires_dt = parse_iso_datetime(expires_text)

                # Filtrar por vigencia: solo mostrar avisos que están activos ahora
                if onset_dt and expires_dt and onset_dt <= now <= expires_dt:
                    print(f"✅ Aviso activo: onset: {onset_dt.strftime('%d/%m/%Y %H:%M')}, expires: {expires_dt.strftime('%d/%m/%Y %H:%M')}, now: {now.strftime('%d/%m/%Y %H:%M')}")

                    # Extraer nivel textual desde <parameter>
                    parametros = info.findall("parameter", namespaces)
                    nivel_textual = None
                    for p in parametros:
                        nombre = p.findtext("valueName", default="", namespaces=namespaces).lower()
                        valor = p.findtext("value", default="", namespaces=namespaces).lower()
                        if "nivel" in nombre:
                            nivel_textual = valor
                            break

                    # Asignar estilo
                    if nivel_textual in colores:
                        # --- INICIO DE MODIFICACIÓN DE ESTILOS ---
                        umap_options = {
                            "color": "#FFFFFF", # Línea blanca finita para delimitar zonas
                            "weight": 1, 
                            "opacity": 1, # Borde completamente opaco
                            "fillColor": colores[nivel_textual], # Color de relleno de alerta
                            "fillOpacity": 1, # Transparencia de relleno
                            "interactive": True
                        }
                        # --- FIN DE MODIFICACIÓN DE ESTILOS ---
                    else:
                        umap_options = {
                            "color": "#FFFFFF", # Color neutro (no se verá por la opacidad)
                            "weight": 0,
                            "opacity": 0,
                            "fillOpacity": 0,
                            "interactive": False
                        }

                    # Construir propiedades para el popup
                    properties = {
                        "areaDesc": area.findtext("areaDesc", default="", namespaces=namespaces),
                        "geocode": area.findtext("geocode/value", default="", namespaces=namespaces),
                        "category": info.findtext("category", default="", namespaces=namespaces),
                        "event": info.findtext("event", default="", namespaces=namespaces),
                        "urgency": info.findtext("urgency", default="", namespaces=namespaces),
                        "severity": info.findtext("severity", default="", namespaces=namespaces),
                        "certainty": info.findtext("certainty", default="", namespaces=namespaces),
                        "effective": info.findtext("effective", default="", namespaces=namespaces),
                        "onset": info.findtext("onset", default="", namespaces=namespaces),
                        "expires": info.findtext("expires", default="", namespaces=namespaces),
                        "senderName": info.findtext("senderName", default="", namespaces=namespaces),
                        "headline": info.findtext("headline", default="", namespaces=namespaces),
                        "web": info.findtext("web", default="", namespaces=namespaces),
                        "contact": info.findtext("contact", default="", namespaces=namespaces),
                        "eventCode": info.findtext("eventCode/value", default="", namespaces=namespaces),
                        "parameter": nivel_textual,
                        "_umap_options": umap_options,
                        # Pasamos los objetos datetime locales para que generate_popup_html los use directamente
                        "popup_html": generate_popup_html(info, area, nivel_textual, onset_dt, expires_dt)    
                    }

                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [parse_coordinates(coordinates)]
                        },
                        "properties": properties
                    }

                    geojson_features.append(feature)
                else:
                    # Aviso descartado por fechas
                    print(f"⏰ Aviso descartado por fechas - archivo: {file_path}")

        return geojson_features

    except Exception as e:
        print(f"Error al procesar el archivo XML {file_path}: {e}")
        return []

# Función para generar el contenido HTML para el popup
def generate_popup_html(info, area, nivel_textual, onset_dt, expires_dt):
    namespaces = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}

    area_desc = area.findtext("areaDesc", default="", namespaces=namespaces)
    headline = info.findtext("headline", default="", namespaces=namespaces)
    description = info.findtext("description", default="", namespaces=namespaces)
    instruction = info.findtext("instruction", default="", namespaces=namespaces)
    web_url = info.findtext("web", default="", namespaces=namespaces)

    # --- INICIO DE CAMBIO: Extraer el tipo de evento y obtener el emoji ---
    event = info.findtext("event", default="Otro", namespaces=namespaces)
    event_display, event_emoji = get_type_and_emoji(event)
    # --- FIN DE CAMBIO ---

    popup_content = (
        f"<b>{headline}</b><br>"
        f"<b>Àrea:</b> {area_desc}<br>"
        f"<b>Nivell d'alerta:</b> <span style='color:{colores.get(nivel_textual, '#000')}'>{nivel_textual.capitalize()}</span><br>"
        # --- NUEVA LÍNEA: Tipus y emoji ---
        f"<b>Tipus:</b> {event_display} {event_emoji}<br>"
        # ----------------------------------
        f"<b>Descripció:</b> {description}<br>"
        f"<b>Instruccions:</b> {instruction}<br>"
        # Usamos los objetos datetime que ya están en la zona horaria de Madrid
        f"<b>Data d'inici:</b> {onset_dt.strftime('%d/%m/%Y %H:%M')}<br>"
        f"<b>Data de fi:</b> {expires_dt.strftime('%d/%m/%Y %H:%M')}<br>"
        f"<b>Més informació: <a href='{web_url}' target='_blank'>AEMET</a>"
    )
    return popup_content
        
# Aquí comienza la nueva función correctamente indentada
def parse_coordinates(coordinates_str):
    coordinates = coordinates_str.split()
    # Las coordenadas de AEMET son lat,lon; GeoJSON es lon,lat
    return [[float(coord.split(',')[1]), float(coord.split(',')[0])] for coord in coordinates]

# Descargar el archivo TAR y procesarlo
download_url = obtener_url_datos_desde_api() # Obtener la URL de datos desde la API
if download_url:
    # Se utiliza una ruta relativa 'avisos.tar' en el código original, la mantengo.
    download_tar(download_url, 'avisos.tar')
    extract_and_process_tar('avisos.tar') # Extraer y procesar los XML
