import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET  # Importamos el módulo para parsear XML
import geojson  # Importamos el módulo para crear archivos GeoJSON
from datetime import datetime, timezone
import pytz


# Leer la URL base desde el config.json
CONFIG_FILE = "config.json"
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

API_URL = config["url_tar"]  # Esta es la URL fija a la API de AEMET con la api_key
TAR_FILE_PATH = "datos/avisos.tar"
EXTRACT_PATH = "datos/geojson_temp"
SALIDA_GEOJSON = "avisos_espana.geojson"

# Mensajes de advertencia según nivel de alerta
WARNING_MESSAGES = {
    "Amarillo": "Tenga cuidado, manténgase informado de las últimas previsiones meteorológicas. Pueden producirse daños moderados a personas y propiedades, especialmente a personas vulnerables o en zonas expuestas.",
    "Naranja": "Esté atento y manténgase al día con las últimas previsiones meteorológicas. Pueden producirse daños moderados a personas y propiedades, especialmente a personas vulnerables o en zonas expuestas.",
    "Rojo": "Tome medidas de precaución, permanezca alerta y actúe según los consejos de las autoridades. Manténgase al día con las últimas previsiones meteorológicas. Viaje solo si su viaje es imprescindible. Pueden producirse daños extremos o catastróficos a personas y propiedades, especialmente a las personas vulnerables o en zonas expuestas."
}

def parse_iso_datetime(date_str):
    try:
        # Convertimos la cadena ISO a objeto datetime con zona horaria incluida
        dt = datetime.fromisoformat(date_str)
        # Convertir a la zona horaria de Madrid (Europe/Madrid)
        madrid_tz = pytz.timezone('Europe/Madrid')
        dt_madrid = dt.astimezone(madrid_tz)
        return dt_madrid
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
        response.raise_for_status()  # Lanza un error si la descarga falla
        with open(download_path, 'wb') as f:
            f.write(response.content)
        print("Archivo TAR descargado correctamente.")
    except Exception as e:
        print(f"Error al descargar el archivo TAR: {e}")

def extract_and_process_tar(tar_path='avisos.tar'):
    try:
        # Extraer el contenido del archivo TAR
        with tarfile.open(tar_path, 'r:*') as tar:
            tar.extractall(path='datos')  # Extrae los archivos en la carpeta 'datos'
        print("Archivos extraídos correctamente.")
        
        all_features = []  # Aquí acumulamos todos los avisos

        # Procesar cada archivo XML extraído
        for file_name in os.listdir('datos'):
            if file_name.endswith('.xml'):
                file_path = os.path.join('datos', file_name)
                features = process_xml_to_geojson(file_path)  # ← ahora devuelve los features
                all_features.extend(features)

        # Leer el archivo GeoJSON existente si existe
        existing_features = []
        if os.path.exists(SALIDA_GEOJSON):
            with open(SALIDA_GEOJSON, 'r') as geojson_file:
                existing_data = json.load(geojson_file)
                existing_features = existing_data.get("features", [])

        # Filtrar solo los avisos activos y no caducados
        now = datetime.now(pytz.timezone('Europe/Madrid'))  # Usamos la zona horaria de Madrid
        filtered_existing_features = []
        for feature in existing_features:
            expires = feature['properties'].get('expires')
            if expires:
                expires_dt = parse_iso_datetime(expires)
                if expires_dt and expires_dt >= now:
                    filtered_existing_features.append(feature)

        # Filtrar los avisos de nivel verde
        filtered_existing_features = [
            feature for feature in filtered_existing_features
            if feature['properties'].get('parameter') != 'verde'
        ]

        # Agrupar por región y seleccionar el aviso más cercano a la fecha de ahora o el de mayor severidad
        region_avisos = {}
        for feature in filtered_existing_features:
            region = feature['properties']['areaDesc']
            onset = parse_iso_datetime(feature['properties']['onset'])
            severity = feature['properties']['severity']
            
            if region not in region_avisos:
                region_avisos[region] = feature
            else:
                existing_feature = region_avisos[region]
                existing_onset = parse_iso_datetime(existing_feature['properties']['onset'])

                # Si el nuevo aviso es más cercano o de mayor severidad, lo seleccionamos
                if (onset > existing_onset) or (severity > existing_feature['properties']['severity']):
                    region_avisos[region] = feature

        # Guardar todos los features en un solo GeoJSON, aunque esté vacío
        geojson_data = {
            "type": "FeatureCollection",
            "features": list(region_avisos.values())  # Solo los más cercanos o de mayor severidad
        }

        try:
            with open(SALIDA_GEOJSON, 'w', encoding='utf-8') as geojson_file:
                json.dump(geojson_data, geojson_file, indent=4)
            print(f"✅ GeoJSON guardado en {SALIDA_GEOJSON} con {len(geojson_data['features'])} avisos.")
        except Exception as e:
            print(f"❌ Error al guardar el GeoJSON: {e}")
    except Exception as e:
        print(f"Error al extraer y procesar el archivo TAR: {e}")

colores = {
    "amarillo": "#f3f702",
    "naranja": "#e6b94e",
    "rojo": "#FF0000"
}

def process_xml_to_geojson(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        namespaces = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
        areas = root.findall(".//info/area", namespaces)
        geojson_features = []
        now = datetime.now(pytz.timezone('Europe/Madrid'))  # Usamos la zona horaria de Madrid


        for area in areas:
            polygon = area.find("polygon", namespaces)
            if polygon is not None:
                coordinates = polygon.text.strip()
                info = root.find(".//info", namespaces)

                # Obtener fechas
                onset_text = info.findtext("onset", default="", namespaces=namespaces)
                expires_text = info.findtext("expires", default="", namespaces=namespaces)
                onset_dt = parse_iso_datetime(onset_text)
                expires_dt = parse_iso_datetime(expires_text)

                # Debug: Ver las fechas que estamos comparando
                print(f"⏰ Aviso en archivo {file_path}: onset: {onset_dt}, expires: {expires_dt}, now: {now}")

                # Filtrar por vigencia: solo mostrar avisos que están activos ahora
                if onset_dt and expires_dt:
                    # Comprobar si el aviso está activo en el día de hoy
                    if onset_dt <= now <= expires_dt:
                        print(f"✅ Aviso activo: onset: {onset_dt}, expires: {expires_dt}, now: {now}")

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
                        umap_options = {
                            "color": colores[nivel_textual],
                            "weight": 3,
                            "opacity": 1,
                            "interactive": True
                        }
                    else:
                        umap_options = {
                            "color": "#FFFFFF",  # Color neutro (no se verá por la opacidad)
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
                    print(f"⏰ Aviso descartado por fechas - onset: {onset_dt}, expires: {expires_dt}, now: {now}")

        return geojson_features

    except Exception as e:
        print(f"Error al procesar el archivo XML {file_path}: {e}")
        return []

# Función para generar el contenido HTML para el popup
def generate_popup_html(info, area, nivel_textual, onset_dt, expires_dt):
    area_desc = area.findtext("areaDesc", default="", namespaces={'': 'urn:oasis:names:tc:emergency:cap:1.2'})
    headline = info.findtext("headline", default="", namespaces={'': 'urn:oasis:names:tc:emergency:cap:1.2'})
    description = info.findtext("description", default="", namespaces={'': 'urn:oasis:names:tc:emergency:cap:1.2'})
    instruction = info.findtext("instruction", default="", namespaces={'': 'urn:oasis:names:tc:emergency:cap:1.2'})
    web_url = info.findtext("web", default="", namespaces={'': 'urn:oasis:names:tc:emergency:cap:1.2'})
    onset_str = onset_dt.strftime("%Y-%m-%d %H:%M:%S") if onset_dt else "No disponible"
    expires_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S") if expires_dt else "No disponible"

    popup_content = (
        f"<b>{headline}</b><br>"  # Título en negrita
        f"<b>Área:</b> {area_desc}</i><br>"  # Área en cursiva
        f"<b>Nivel de alerta:</b> <span style='color:{colores.get(nivel_textual, '#000')}'>{nivel_textual.capitalize()}</span></i><br>"  # Nivel de alerta en cursiva
        f"<b>Descripción:</b> {description}<br>"  # Descripción en negrita
        f"<b>Instrucciones:</b> {instruction}<br>"  # Instrucciones en negrita
        f"<b>Fecha de inicio:</b> {onset_str}<br>"  # Fecha de inicio en negrita
        f"<b>Fecha de fin:</b> {expires_str}<br>"  # Fecha de fin en negrita
        f"<b>Más información:</b> <a href='{web_url}' target='_blank'>AEMET</a><br>"  # Enlace a más información en negrita
    )
    return popup_content
        
# Aquí comienza la nueva función correctamente indentada
def parse_coordinates(coords_string):
    """
    Convierte una cadena de coordenadas separadas por espacio en una lista de tuplas.
    """
    try:
        coords = coords_string.split()
        coords = [tuple(map(float, coord.split(','))) for coord in coords]
        return coords
    except Exception as e:
        print(f"Error al procesar coordenadas: {e}")
        return []

# Descargar el archivo TAR y procesarlo
download_url = obtener_url_datos_desde_api()  # Obtener la URL de datos desde la API
if download_url:
    download_tar(download_url)  # Descargar el archivo TAR
    extract_and_process_tar()  # Extraer y procesar los XML
