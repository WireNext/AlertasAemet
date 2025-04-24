import geojson
from shapely.geometry import Point
import json

# Función para filtrar los avisos que están dentro de los límites de España
def filtrar_avisos_espana(avisos):
    avisos_filtrados = []
    for aviso in avisos:
        lat = aviso['coordenada']['lat']
        lon = aviso['coordenada']['lon']

        # Verificar si la coordenada está dentro de los límites geográficos de España
        if 36 <= lat <= 43 and -10 <= lon <= 4:
            avisos_filtrados.append(aviso)
    
    return avisos_filtrados

# Función para generar el archivo GeoJSON con los avisos filtrados
def generar_geojson(avisos_filtrados):
    feature_collection = {
        'type': 'FeatureCollection',
        'features': []
    }
    
    for aviso in avisos_filtrados:
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [aviso['coordenada']['lon'], aviso['coordenada']['lat']]
            },
            'properties': aviso['properties']
        }
        feature_collection['features'].append(feature)
    
    # Guardar el archivo GeoJSON generado
    with open('avisos_filtrados.geojson', 'w') as f:
        geojson.dump(feature_collection, f, indent=4)

# Cargar los avisos (ajustar según tu archivo de entrada)
def cargar_avisos():
    # Simulamos algunos avisos para este ejemplo
    return [
        {'coordenada': {'lat': 40.0, 'lon': -3.0}, 'properties': {'aviso': 'Amarillo', 'tipo': 'Cielo'}},
        {'coordenada': {'lat': 42.5, 'lon': -7.0}, 'properties': {'aviso': 'Rojo', 'tipo': 'Viento'}},
        {'coordenada': {'lat': 36.0, 'lon': -6.0}, 'properties': {'aviso': 'Naranja', 'tipo': 'Lluvias'}},
        {'coordenada': {'lat': 34.5, 'lon': -5.0}, 'properties': {'aviso': 'Rojo', 'tipo': 'Viento'}},  # Fuera de España
        # Más avisos...
    ]

# Main: cargar los avisos y filtrar
def main():
    # Cargar los avisos (ajustar según tu formato)
    avisos = cargar_avisos()

    # Filtrar los avisos dentro de los límites de España
    avisos_filtrados = filtrar_avisos_espana(avisos)

    # Generar el archivo GeoJSON con los avisos filtrados
    generar_geojson(avisos_filtrados)

    print(f'GeoJSON generado con {len(avisos_filtrados)} avisos dentro de los límites de España.')

if __name__ == '__main__':
    main()
