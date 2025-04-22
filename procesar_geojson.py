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
    "Rojo": "#FF0000"      # Rojo
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

# Función para convertir el XML a GeoJSON
def process_xml_to_geojson(file_path):
    try:
        # Parsear el XML
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Definir el espacio de nombres del XML
        ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        
        # Buscar los datos dentro de los elementos 'info'
        for info in root.findall('cap:info', ns):
            # Obtener la descripción del evento
            event = info.find('cap:event', ns).text
            headline = info.find('cap:headline', ns).text
            description = info.find('cap:description', ns).text
            
            # Obtener las coordenadas del polígono
            polygon_data = info.find('.//cap:polygon', ns).text
            coordinates = [tuple(map(float, coord.split(','))) for coord in polygon_data.split()]
            
            # Obtener el nivel de alerta
            level = None
            for param in info.findall('cap:parameter', ns):
                value_name = param.find('cap:valueName', ns).text
                if value_name == 'AEMET-Meteoalerta nivel':
                    level = param.find('cap:value', ns).text
            
            # Crear el objeto GeoJSON
            feature = geojson.Feature(
                geometry=geojson.Polygon([coordinates]),
                properties={
                    'event': event,
                    'headline': headline,
                    'description': description,
                    'alert_level': level,  # Añadimos el nivel de alerta
                }
            )
            
            # Guardar como GeoJSON
            geojson_data = geojson.FeatureCollection([feature])
            geojson_filename = file_path.replace('.xml', '.geojson')
            with open(geojson_filename, 'w') as f:
                geojson.dump(geojson_data, f, indent=4)
            
            print(f"GeoJSON generado correctamente para {file_path}.")
    except Exception as e:
        print(f"Error al procesar el archivo XML {file_path}: {e}")

# Descargar el archivo TAR y procesarlo
download_url = obtener_url_datos_desde_api()  # Obtener la URL de datos desde la API
if download_url:
    download_tar(download_url)  # Descargar el archivo TAR
    extract_and_process_tar()  # Extraer y procesar los XML
