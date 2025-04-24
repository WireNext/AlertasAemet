import json
import requests
import tarfile
import os

# Cargar configuración
with open('config.json', 'r') as f:
    config = json.load(f)

# Obtener la URL desde el campo 'datos'
datos_url = config['datos']

# Descargar el archivo .tar
print(f"Descargando el archivo desde: {datos_url}")
response = requests.get(datos_url)

# Verificar si la descarga fue exitosa
if response.status_code == 200:
    # Guardar el archivo .tar en el disco
    tar_file_path = 'avisos.tar'
    with open(tar_file_path, 'wb') as f:
        f.write(response.content)
    print(f"Archivo {tar_file_path} descargado correctamente.")
else:
    print(f"Error al descargar el archivo. Código de estado: {response.status_code}")
    exit(1)

# Extraer el archivo .tar
if tarfile.is_tarfile(tar_file_path):
    with tarfile.open(tar_file_path, 'r') as tar:
        tar.extractall(path='.')
        print("Archivos extraídos correctamente.")
else:
    print("El archivo descargado no es un archivo .tar válido.")
    exit(1)

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
