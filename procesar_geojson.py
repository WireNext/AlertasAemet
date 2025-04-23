import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET  # Importamos el módulo para parsear XML
import geojson  # Importamos el módulo para crear archivos GeoJSON


# Leer la URL base desde el config.json
CONFIG_FILE = "config.json"
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

API_URL = config["url_tar"]  # Esta es la URL fija a la API de AEMET con la api_key
TAR_FILE_PATH = "datos/avisos.tar"
EXTRACT_PATH = "datos/geojson_temp"
SALIDA_GEOJSON = "avisos_espana.geojson"

# Definir colores según el nivel de aviso
COLORS = {
    "Amarillo": "#FFFF00",  # Amarillo
    "Naranja": "#FFA500",  # Naranja
    "Rojo": "#FF0000",      # Rojo
    "verde": "#3cc962",
}

# Mensajes de advertencia según nivel de alerta
WARNING_MESSAGES = {
    "Amarillo": "Tenga cuidado, manténgase informado de las últimas previsiones meteorológicas. Pueden producirse daños moderados a personas y propiedades, especialmente a personas vulnerables o en zonas expuestas.",
    "Naranja": "Esté atento y manténgase al día con las últimas previsiones meteorológicas. Pueden producirse daños moderados a personas y propiedades, especialmente a personas vulnerables o en zonas expuestas.",
    "Rojo": "Tome medidas de precaución, permanezca alerta y actúe según los consejos de las autoridades. Manténgase al día con las últimas previsiones meteorológicas. Viaje solo si su viaje es imprescindible. Pueden producirse daños extremos o catastróficos a personas y propiedades, especialmente a las personas vulnerables o en zonas expuestas."
}

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

# Función para extraer el archivo TAR y procesar los XML
def extract_and_process_tar(tar_path='avisos.tar'):
    try:
        # Extraer el contenido del archivo TAR
        with tarfile.open(tar_path, 'r:*') as tar:
            tar.extractall(path='datos')  # Extrae los archivos en la carpeta 'datos'
        print("Archivos extraídos correctamente.")
        
        # Procesar cada archivo XML extraído
        for file_name in os.listdir('datos'):
            if file_name.endswith('.xml'):
                file_path = os.path.join('datos', file_name)
                process_xml_to_geojson(file_path)

    except Exception as e:
        print(f"Error al extraer y procesar el archivo TAR: {e}")

def process_xml_to_geojson(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        namespaces = {'': 'urn:oasis:names:tc:emergency:cap:1.2'}
        areas = root.findall(".//info/area", namespaces)
        geojson_features = []

    for area in areas:
        polygon = area.find("polygon", namespaces)
        if polygon is not None:
            coordinates = polygon.text.strip()

        # Navegar al nodo 'info' correspondiente
            info = root.find(".//info", namespaces)

        # Obtener detalles del aviso
            category = info.findtext("category", default="", namespaces=namespaces)
            event = info.findtext("event", default="", namespaces=namespaces)
            responseType = info.findtext("responseType", default="", namespaces=namespaces)
            urgency = info.findtext("urgency", default="", namespaces=namespaces)
            severity = info.findtext("severity", default="", namespaces=namespaces)
            certainty = info.findtext("certainty", default="", namespaces=namespaces)
            effective = info.findtext("effective", default="", namespaces=namespaces)
            onset = info.findtext("onset", default="", namespaces=namespaces)
            expires = info.findtext("expires", default="", namespaces=namespaces)
            senderName = info.findtext("senderName", default="", namespaces=namespaces)
            headline = info.findtext("headline", default="", namespaces=namespaces)
            web = info.findtext("web", default="", namespaces=namespaces)
            contact = info.findtext("contact", default="", namespaces=namespaces)

        # Obtener parámetros especiales
            eventCode = info.findtext("eventCode/value", default="", namespaces=namespaces)
            parameter = info.findtext("parameter/value", default="", namespaces=namespaces)

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [parse_coordinates(coordinates)]
                },
                "properties": {
                    "areaDesc": area.findtext("areaDesc", default="", namespaces=namespaces),
                    "geocode": area.findtext("geocode/value", default="", namespaces=namespaces),
                    "category": category,
                    "event": event,
                    "responseType": responseType,
                    "urgency": urgency,
                    "severity": severity,
                    "certainty": certainty,
                    "effective": effective,
                    "onset": onset,
                    "expires": expires,
                    "senderName": senderName,
                    "headline": headline,
                    "web": web,
                    "contact": contact,
                    "eventCode": eventCode,
                    "parameter": parameter
                }
            }
            geojson_features.append(feature)

        if geojson_features:
            geojson = {
                "type": "FeatureCollection",
                "features": geojson_features
            }
            geojson_file_path = "avisos_espana.geojson"
            with open(geojson_file_path, 'w') as geojson_file:
                json.dump(geojson, geojson_file, indent=4)
            print(f"GeoJSON generado correctamente para {file_path}")
        else:
            print(f"Archivo XML {file_path} no contiene datos válidos para generar un GeoJSON.")
    except Exception as e:
        print(f"Error al procesar el archivo XML {file_path}: {e}")

# Aquí comienza la nueva función correctamente indentada
def parse_coordinates(coordinates_str):
    coordinates = coordinates_str.split()
    return [[float(coord.split(',')[1]), float(coord.split(',')[0])] for coord in coordinates]

# Descargar el archivo TAR y procesarlo
download_url = obtener_url_datos_desde_api()  # Obtener la URL de datos desde la API
if download_url:
    download_tar(download_url)  # Descargar el archivo TAR
    extract_and_process_tar()  # Extraer y procesar los XML
