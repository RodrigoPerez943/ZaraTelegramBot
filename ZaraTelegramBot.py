import requests
from bs4 import BeautifulSoup
import time
import os
import json
import logging

# Configuración de Logging
logging.basicConfig(
    filename='monitor_zara.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuración
INTERVALO_SEGUNDOS = 60  # Intervalo entre verificaciones en segundos
ARCHIVO_LINKS = 'links.txt'  # Archivo que contiene los enlaces de los productos
ESTADOS_FILE = 'estados.json'  # Archivo para almacenar estados previos

# Configuración de Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'Tu token aquí')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'Tu id aquí')

# Expresión regular para validar enlaces de Zara (opcional)
import re

def validar_enlace_zara(url):
    # Permite URLs con o sin '/share/'
    pattern = r'https?://(www\.)?zara\.com/(?:share/)?.*/p\d+\.html'
    return re.match(pattern, url) is not None

# Función para leer los enlaces desde el archivo
def leer_links(archivo):
    try:
        with open(archivo, 'r') as f:
            links = [linea.strip() for linea in f if linea.strip()]
        return links
    except FileNotFoundError:
        logging.error(f"El archivo {archivo} no fue encontrado.")
        return []

# Función para enviar mensaje de Telegram usando requests
def enviar_mensaje_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': mensaje,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=payload)
        if not response.ok:
            logging.error(f"Error al enviar mensaje de Telegram: {response.text}")
        else:
            logging.info("Mensaje enviado exitosamente.")
    except Exception as e:
        logging.error(f"Error al enviar mensaje de Telegram: {e}")

# Función para verificar la disponibilidad, obtener el nombre del producto y las tallas
def verificar_disponibilidad(link, headers):
    try:
        respuesta = requests.get(link, headers=headers, timeout=10)
        if respuesta.status_code != 200:
            logging.error(f"Error al acceder a {link}: Código de estado {respuesta.status_code}")
            return {'nombre': 'Desconocido', 'estado': 'ERROR', 'tallas': None}

        soup = BeautifulSoup(respuesta.text, 'html.parser')

        # Obtener el nombre del producto
        h1_nombre = soup.find('h1', class_='product-detail-info__header-name', attrs={'data-qa-qualifier': 'product-detail-info-name'})
        if h1_nombre:
            nombre_producto = h1_nombre.get_text(strip=True)
        else:
            nombre_producto = 'Desconocido'

        # Buscar el elemento que indica si está agotado
        span_agotado = soup.find('span', class_='product-detail-show-similar-products__action-tip')
        if span_agotado and 'AGOTADO' in span_agotado.get_text(strip=True).upper():
            estado = 'AGOTADO'
            tallas = None  # No se extraen tallas si está agotado
            logging.info(f"{nombre_producto} está AGOTADO.")
        else:
            # Buscar el botón "Añadir" que indica disponibilidad
            boton_anadir = soup.find('div', class_='zds-button__lines-wrapper')
            if boton_anadir and 'Añadir' in boton_anadir.get_text(strip=True):
                estado = 'DISPONIBLE'
                tallas = extraer_tallas(soup)
                logging.info(f"{nombre_producto} está DISPONIBLE.")
            else:
                # Si no se encuentra ninguna de las dos opciones
                estado = 'INDETERMINADO'
                tallas = extraer_tallas(soup)
                logging.info(f"{nombre_producto} tiene estado INDETERMINADO.")

        return {'nombre': nombre_producto, 'estado': estado, 'tallas': tallas}

    except requests.RequestException as e:
        logging.error(f"Error al acceder a {link}: {e}")
        return {'nombre': 'Desconocido', 'estado': 'ERROR', 'tallas': None}

# Función para extraer las tallas y su estado
def extraer_tallas(soup):
    tallas = []
    # Encontrar la sección que contiene las tallas
    size_selector = soup.find('ul', class_='size-selector-sizes size-selector-sizes--grid-gap', role='listbox')
    if not size_selector:
        logging.info("No se encontraron tallas disponibles.")
        return tallas  # Retorna lista vacía si no hay tallas disponibles

    li_tallas = size_selector.find_all('li', class_='size-selector-sizes__size')
    for li in li_tallas:
        button = li.find('button', class_='size-selector-sizes-size__button')
        if not button:
            continue  # Salta si no hay botón

        data_action = button.get('data-qa-action', '')
        size_label = button.find('div', class_='size-selector-sizes-size__label')
        if size_label:
            talla = size_label.get_text(strip=True)
        else:
            talla = 'Desconocido'

        # Determinar el estado de la talla
        if 'size-in-stock' in data_action:
            estado_talla = 'Disponible'
        elif 'size-low-on-stock' in data_action:
            estado_talla = 'Pocas unidades'
        elif 'size-out-of-stock' in data_action:
            estado_talla = 'Sin disponibilidad'
        else:
            estado_talla = 'Estado desconocido'

        # Solo agregar tallas disponibles o con pocas unidades
        if estado_talla == 'Sin disponibilidad':
            continue  # No se agrega si no hay tallas disponibles
        tallas.append({'talla': talla, 'estado': estado_talla})

    if tallas:
        logging.info(f"Tallas disponibles: {[t['talla'] for t in tallas]}")
    else:
        logging.info("No hay tallas disponibles o todas están sin disponibilidad.")
    return tallas if tallas else None  # Retorna None si no hay tallas disponibles

# Función para cargar estados previos desde el archivo JSON
def cargar_estados(links):
    if os.path.exists(ESTADOS_FILE):
        try:
            with open(ESTADOS_FILE, 'r') as f:
                estados = json.load(f)
            # Asegurarse de que todos los links estén en el diccionario
            for link in links:
                if link not in estados:
                    estados[link] = {'nombre': 'Desconocido', 'estado': 'DESCONOCIDO', 'tallas': None}
            return estados
        except json.JSONDecodeError:
            logging.error(f"Error al leer {ESTADOS_FILE}. Iniciando con estados desconocidos.")
    # Si el archivo no existe o hay un error, inicializar con 'DESCONOCIDO'
    return {link: {'nombre': 'Desconocido', 'estado': 'DESCONOCIDO', 'tallas': None} for link in links}

# Función para guardar estados actuales en el archivo JSON
def guardar_estados(estados):
    try:
        with open(ESTADOS_FILE, 'w') as f:
            json.dump(estados, f, indent=4)
        logging.info("Estados guardados correctamente.")
    except Exception as e:
        logging.error(f"Error al guardar estados: {e}")

# Función para enviar la notificación inicial con el estado de todos los productos
def enviar_notificacion_inicial(estados):
    mensaje = "<b>Estado Inicial de Productos en Zara:</b>\n\n"
    for link, info in estados.items():
        nombre = info['nombre']
        estado = info['estado']
        tallas = info['tallas']
        estado_mensaje = estado if estado != 'ERROR' else 'Error al verificar'

        mensaje += f"<a href='{link}'>{nombre}</a>: {estado_mensaje}"

        # Añadir tallas si están disponibles
        if tallas:
            mensaje += "\nTallas Disponibles:"
            for talla_info in tallas:
                talla = talla_info['talla']
                estado_talla = talla_info['estado']
                if estado_talla == 'Pocas unidades':
                    # Usar un emoji para indicar pocas unidades
                    mensaje += f"\n- <b>{talla}</b>: 🟡 Pocas unidades"
                else:
                    mensaje += f"\n- <b>{talla}</b>: Disponible"
        mensaje += "\n\n"
    enviar_mensaje_telegram(mensaje)

def main():
    # Leer los enlaces de productos
    links = leer_links(ARCHIVO_LINKS)
    if not links:
        print("No hay enlaces para verificar.")
        logging.info("No hay enlaces para verificar. Terminando script.")
        return

    # Encabezados para simular un navegador
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
                      'AppleWebKit/537.36 (KHTML, like Gecko) ' +
                      'Chrome/91.0.4472.124 Safari/537.36'
    }

    # Cargar estados previos
    estados_previos = cargar_estados(links)

    # Realizar la verificación inicial
    print("Realizando verificación inicial de productos...")
    logging.info("Realizando verificación inicial de productos...")
    estados_actuales = {}
    for link in links:
        info = verificar_disponibilidad(link, headers)
        estados_actuales[link] = info
        print(f"{link}: {info['estado']}")

    # Enviar notificación inicial
    enviar_notificacion_inicial(estados_actuales)

    # Actualizar y guardar los estados previos
    estados_previos = estados_actuales.copy()
    guardar_estados(estados_previos)

    print("Inicio de la monitorización de productos en Zara con notificaciones de Telegram.")
    logging.info("Inicio de la monitorización de productos en Zara con notificaciones de Telegram.")
    try:
        while True:
            print(f"\n[Verificación realizada a las {time.strftime('%Y-%m-%d %H:%M:%S')}]")
            logging.info(f"[Verificación realizada a las {time.strftime('%Y-%m-%d %H:%M:%S')}]")
            cambios = []
            for link in links:
                info_actual = verificar_disponibilidad(link, headers)
                estado_actual = info_actual['estado']
                nombre_producto = info_actual['nombre']
                tallas_actuales = info_actual['tallas']
                info_previo = estados_previos.get(link, {'nombre': 'Desconocido', 'estado': 'DESCONOCIDO', 'tallas': None})
                estado_previo = info_previo['estado']

                # Detectar cambios de AGOTADO a DISPONIBLE
                if estado_previo == 'AGOTADO' and estado_actual == 'DISPONIBLE':
                    mensaje = f"✅ <a href='{link}'>{nombre_producto}</a>: ¡Disponible!"

                    # Añadir información de tallas si están disponibles
                    if tallas_actuales:
                        mensaje += "\nTallas Disponibles:"
                        for talla_info in tallas_actuales:
                            talla = talla_info['talla']
                            estado_talla = talla_info['estado']
                            if estado_talla == 'Pocas unidades':
                                mensaje += f"\n- <b>{talla}</b>: 🟡 Pocas unidades"
                            else:
                                mensaje += f"\n- <b>{talla}</b>: Disponible"

                    cambios.append(mensaje)
                    enviar_mensaje_telegram(mensaje)

                # Actualizar el estado previo
                estados_previos[link] = info_actual

                print(f"{link}: {estado_actual}")
                logging.info(f"{link}: {estado_actual}")

            # Guardar los estados después de la verificación
            guardar_estados(estados_previos)

            # Opcional: Enviar un resumen diario o periódico si hay cambios
            if cambios:
                print(f"Se enviaron {len(cambios)} notificaciones de disponibilidad.")
                logging.info(f"Se enviaron {len(cambios)} notificaciones de disponibilidad.")

            print(f"Esperando {INTERVALO_SEGUNDOS} segundos para la siguiente verificación...\n")
            logging.info(f"Esperando {INTERVALO_SEGUNDOS} segundos para la siguiente verificación...\n")
            time.sleep(INTERVALO_SEGUNDOS)
    except KeyboardInterrupt:
        print("\nMonitorización terminada por el usuario.")
        logging.info("Monitorización terminada por el usuario.")
        guardar_estados(estados_previos)

if __name__ == "__main__":
    main()
