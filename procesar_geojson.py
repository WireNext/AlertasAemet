import json
import os
import shutil
import requests
import tarfile
import xml.etree.ElementTree as ET  # Importamos el módulo para parsear XML
import geojson  # Importamos el módulo para crear archivos GeoJSON
from datetime import datetime, timezone



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

def extract_and_process_tar(tar_path='avisos.tar'):
    try:
        # Extraer el contenido del archivo TAR
        with tarfile.open(tar_path, 'r:*') as tar:
            tar.extractall(path='datos')  # Extrae los archivos en la carpeta 'datos'
        print("Archivos extraídos correctamente.")
        
        all_features = []

        # Procesar cada archivo XML extraído
        for file_name in os.listdir('datos'):
            if file_name.endswith('.xml'):
                file_path = os.path.join('datos', file_name)
                features = process_xml_to_geojson(file_path)
                if features:
                    all_features.extend(features)

        if all_features:
            geojson_data = {
                "type": "FeatureCollection",
                "features": all_features
            }
            with open("avisos_espana.geojson", 'w', encoding="utf-8") as geojson_file:
                json.dump(geojson_data, geojson_file, indent=4, ensure_ascii=False)
            print(f"✅ GeoJSON generado correctamente con {len(all_features)} avisos.")
        else:
            print("⚠️ No se encontraron avisos válidos en los archivos XML.")
    except Exception as e:
        print(f"❌ Error al extraer y procesar el archivo TAR: {e}")

def process_xml_to_geojson(xml_file_path):
    ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    features = []

    # Definir límites de latitud y longitud para España
    min_lat, max_lat = 36.0, 43.5  # Latitudes de España
    min_lon, max_lon = -9.5, 3.5   # Longitudes de España

    # Buscamos los bloques <info> en español
    for info in root.findall('cap:info', ns):
        language = info.findtext('cap:language', default='', namespaces=ns)
        if language != 'es-ES':
            continue  # saltamos si no es español

        event = info.findtext('cap:event', default='', namespaces=ns)
        severity = info.findtext('cap:severity', default='', namespaces=ns)
        onset = info.findtext('cap:onset', default='', namespaces=ns)
        expires = info.findtext('cap:expires', default='', namespaces=ns)
        headline = info.findtext('cap:headline', default='', namespaces=ns)
        description = info.findtext('cap:description', default='', namespaces=ns)
        instruction = info.findtext('cap:instruction', default='', namespaces=ns)
        web = info.findtext('cap:web', default='', namespaces=ns)

        # Leemos todos los elementos <area>
        for area in info.findall('cap:area', ns):
            area_desc = area.findtext('cap:areaDesc', default='', namespaces=ns)
            polygon_text = area.findtext('cap:polygon', default='', namespaces=ns)

            if not polygon_text:
                continue

            coords = []
            for coord in polygon_text.strip().split():
                lat, lon = map(float, coord.split(','))
                coords.append([lon, lat])  # GeoJSON usa lon,lat

                # Verificar coordenadas fuera de los límites
                if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                    print(f"Coordenada fuera de los límites: {coord} en el área {area_desc}")

            # Filtrar polígonos con demasiados vértices (esto es solo una medida para identificar problemas)
            if len(coords) > 200:  # Número arbitrario de vértices para ser un polígono "sospechoso"
                print(f"Polígono con más de 200 vértices en el área {area_desc}. Número de vértices: {len(coords)}")

            # Cerramos el polígono si no lo está
            if coords[0] != coords[-1]:
                coords.append(coords[0])

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                },
                "properties": {
                    "evento": event,
                    "nivel": severity,
                    "inicio": onset,
                    "fin": expires,
                    "titulo": headline,
                    "descripcion": description,
                    "instrucciones": instruction,
                    "zona": area_desc,
                    "web": web
                }
            }
            features.append(feature)

    return features
        
# Aquí comienza la nueva función correctamente indentada
def parse_coordinates(coordinates_str):
    coordinates = coordinates_str.split()
    return [[float(coord.split(',')[1]), float(coord.split(',')[0])] for coord in coordinates]

# Descargar el archivo TAR y procesarlo
download_url = obtener_url_datos_desde_api()  # Obtener la URL de datos desde la API
if download_url:
    download_tar(download_url)  # Descargar el archivo TAR
    extract_and_process_tar()  # Extraer y procesar los XML
