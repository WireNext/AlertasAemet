import json
import requests
import tarfile
import os
from datetime import datetime
import xml.etree.ElementTree as ET
import geojson

# Paso 1: Leer el archivo config.json para obtener el enlace al archivo .tar
with open('config.json', 'r') as f:
    config = json.load(f)
    datos_url = config['datos']

# Paso 2: Descargar el archivo .tar
print("Descargando archivo .tar...")
response = requests.get(datos_url)
tar_file = "avisos.tar"

with open(tar_file, 'wb') as f:
    f.write(response.content)
print("Archivo .tar descargado correctamente.")

# Paso 3: Extraer el archivo .tar
print("Extrayendo el archivo .tar...")
with tarfile.open(tar_file, 'r') as tar:
    tar.extractall(path="avisos")
print("Archivo .tar extraído correctamente.")

# Paso 4: Procesar los XML y filtrar por la fecha de hoy
fecha_hoy = datetime.now().strftime('%Y-%m-%d')
avisos_filtrados = []

# Buscar archivos XML extraídos
for root, dirs, files in os.walk("avisos"):
    for file in files:
        if file.endswith('.xml'):
            xml_file = os.path.join(root, file)
            
            # Parsear el XML
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Buscar la fecha del aviso
            fecha_aviso = root.find(".//FechaEmision")
            if fecha_aviso is not None:
                fecha_aviso = fecha_aviso.text[:10]  # Solo tomamos la fecha (YYYY-MM-DD)
                
                # Filtrar avisos que corresponden a la fecha de hoy
                if fecha_aviso == fecha_hoy:
                    avisos_filtrados.append(root)

print(f"Se han encontrado {len(avisos_filtrados)} avisos para hoy ({fecha_hoy}).")

# Paso 5: Procesar los avisos y preparar el GeoJSON
# Crear la estructura de GeoJSON
geojson_data = {
    "type": "FeatureCollection",
    "features": []
}

# Extraer datos de los avisos filtrados
for aviso in avisos_filtrados:
    area = aviso.find(".//Area")
    if area is not None:
        nombre_area = area.text
        coordenadas = area.attrib.get('coordenadas', None)  # Asumiendo que las coordenadas están en el atributo 'coordenadas'
        
        if coordenadas:
            # Crear la Feature para el GeoJSON
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": list(map(float, coordenadas.split(',')))
                },
                "properties": {
                    "area": nombre_area,
                    "fecha_aviso": fecha_hoy,
                    "descripcion": aviso.find(".//Descripcion").text if aviso.find(".//Descripcion") is not None else "Sin descripción"
                }
            }
            geojson_data["features"].append(feature)

# Guardar el GeoJSON como avisos_espana.geojson
geojson_file = "avisos_espana.geojson"
with open(geojson_file, 'w') as f:
    geojson.dump(geojson_data, f)

print(f"GeoJSON generado correctamente en {geojson_file}.")
