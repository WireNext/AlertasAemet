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
        
        # Aquí va el procesamiento del XML para convertirlo a GeoJSON
        features = []
        
        for element in root.findall('.//someElement'):  # Aquí se puede ajustar según la estructura del XML
            # Verificamos si el elemento tiene un valor no nulo
            if element.text is not None:
                some_value = element.text
            else:
                some_value = "valor por defecto"  # O cualquier otro manejo adecuado

            # Ejemplo de cómo construir una Feature de GeoJSON
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",  # O el tipo de geometría que corresponda
                    "coordinates": [0.0, 0.0]  # Aquí se deben poner las coordenadas correctas
                },
                "properties": {
                    "value": some_value
                }
            }

            features.append(feature)

        # Si hay características (features), construimos el objeto GeoJSON
        if features:
            geojson_data = {
                "type": "FeatureCollection",
                "features": features
            }

            # Guardamos el archivo GeoJSON con el mismo nombre que el archivo XML
            geojson_filename = os.path.splitext(file_path)[0] + ".geojson"
            with open(geojson_filename, 'w') as geojson_file:
                geojson.dump(geojson_data, geojson_file)

            print(f"GeoJSON generado correctamente para {file_path}")

        else:
            print(f"Archivo XML {file_path} no contiene datos válidos para generar un GeoJSON.")

    except Exception as e:
        # Si ocurre algún error, lo registramos y continuamos con el siguiente archivo
        print(f"Error al procesar el archivo XML {file_path}: {e}")
        pass
# Descargar el archivo TAR y procesarlo
download_url = obtener_url_datos_desde_api()  # Obtener la URL de datos desde la API
if download_url:
    download_tar(download_url)  # Descargar el archivo TAR
    extract_and_process_tar()  # Extraer y procesar los XML
