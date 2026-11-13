
import os
import re
import csv
import time
from pathlib import Path
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

# ==================================================
# CONFIGURACION
# ==================================================

URL_UPCOMING = (
    "https://www.bet365.pe/#/AC/B1/C1/"
    "D1002/G40/J99/Q1/F%5E2001/"
)

RUTAS_BRAVE = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    os.path.expandvars(
        r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
    ),
]

BRAVE = next(
    (ruta for ruta in RUTAS_BRAVE if os.path.exists(ruta)),
    None
)

ARCHIVO_SALIDA = Path("cuotas_partidos.csv")

TIEMPO_UPCOMING = 20
TIEMPO_DETALLE = 15
TIEMPO_REINTENTO = 2

MERCADOS_OBJETIVO = {
    "40": "Resultado del partido",
    "10114": "Doble oportunidad"
}


# ==================================================
# VARIABLES DE CAPTURA
# ==================================================

contenido_upcoming = None
contenidos_upcoming = []

fi_actual = None
contenido_detalle = None
url_detalle = None


# ==================================================
# ESCUCHAR RESPUESTAS DE BET365
# ==================================================

def escuchar_respuestas(response):

    global contenido_upcoming
    global contenidos_upcoming
    global contenido_detalle
    global url_detalle

    url = response.url

    if response.status != 200:
        return

    # UPCOMING: GUARDAR TODAS LAS RESPUESTAS

    if "matchmarketscontentapi/soccerupcomingmatches" in url:

        try:
            contenido = response.text()

            if contenido and len(contenido) > 100:

                contenido_upcoming = contenido

                # Evitar respuestas duplicadas.
                if contenido not in contenidos_upcoming:
                    contenidos_upcoming.append(contenido)

                    print(
                        f"[UPCOMING] Nueva respuesta capturada: "
                        f"{len(contenido):,} caracteres"
                    )

        except Exception as error:
            print("[ERROR UPCOMING]", error)

    # DETALLE DEL PARTIDO

    if "matchbettingcontentapi/coupon" in url:

        if not fi_actual:
            return

        url_decodificada = unquote(url)

        if f"E{fi_actual}#" not in url_decodificada:
            return

        try:
            contenido = response.text()

            if contenido:
                contenido_detalle = contenido
                url_detalle = url

                print(
                    f"[DETALLE] FI={fi_actual} | "
                    f"{len(contenido):,} caracteres"
                )

        except Exception as error:
            print("[ERROR DETALLE]", error)


# ==================================================
# ESPERAR RESPUESTA
# ==================================================

def esperar_respuesta(pagina, tipo, timeout=5):

    global contenido_upcoming
    global contenido_detalle

    inicio = time.monotonic()

    while time.monotonic() - inicio < timeout:

        if tipo == "upcoming":

            if contenido_upcoming and len(contenido_upcoming) > 1000:
                return True

        elif tipo == "detalle":

            if contenido_detalle and len(contenido_detalle) > 1000:

                if "|EV;" in contenido_detalle and "|MG;" in contenido_detalle:
                    return True

        pagina.wait_for_timeout(100)

    return False


# ==================================================
# ESPERAR NUEVO ENDPOINT UPCOMING
# ==================================================

def esperar_nuevo_upcoming(pagina, cantidad_anterior, timeout=2):

    inicio = time.monotonic()

    while time.monotonic() - inicio < timeout:

        if len(contenidos_upcoming) > cantidad_anterior:
            return True

        pagina.wait_for_timeout(100)

    return False


# ==================================================
# DETECTAR Y DESPLEGAR COMPETICIONES CERRADAS
# ==================================================




def desplegar_competiciones(pagina):

    global contenido_upcoming

    print("\n" + "=" * 65)
    print("DETECTANDO Y DESPLEGANDO COMPETICIONES")
    print("=" * 65)

    selector = ".rrc-d5"

    # ==========================================
    # FUNCION INTERNA PARA RECUPERAR LA PAGINA
    # ==========================================

    def recuperar_pagina():

        global contenido_upcoming

        print("\n[RECUPERACION] Recargando Bet365...")

        try:

            contenido_upcoming = None

            pagina.reload(
                wait_until="domcontentloaded",
                timeout=30000
            )

            # Esperar nuevamente los contenedores.

            inicio = time.monotonic()

            while time.monotonic() - inicio < 15:

                if pagina.locator(selector).count() > 0:
                    break

                pagina.wait_for_timeout(250)

            # Esperar snapshot actualizado.

            esperar_respuesta(
                pagina,
                "upcoming",
                timeout=8
            )

            cantidad_actual = pagina.locator(selector).count()

            if cantidad_actual > 0:

                print(
                    "[RECUPERACION OK] Página restaurada. "
                    f"Competiciones: {cantidad_actual}"
                )

                return True

            print(
                "[ERROR] La página recargó, "
                "pero no aparecieron las competiciones."
            )

            return False

        except Exception as error:

            print("[ERROR RECUPERACION]", error)

            return False

    # ==========================================
    # DETECTAR COMPETICIONES
    # ==========================================

    inicio = time.monotonic()
    cantidad = 0

    while time.monotonic() - inicio < 10:

        cantidad = pagina.locator(selector).count()

        if cantidad > 0:
            break

        pagina.wait_for_timeout(250)

    print(f"[INFO] Competiciones detectadas: {cantidad}")

    if cantidad == 0:

        print("[ERROR] No aparecieron los contenedores .rrc-d5")

        return

    # Guardar nombres iniciales para identificarlos
    # después de las recargas.

    nombres_competiciones = []

    bloques = pagina.locator(selector)

    for indice in range(cantidad):

        try:

            nombre = (
                bloques.nth(indice)
                .locator(".rrc-74a")
                .inner_text(timeout=3000)
                .strip()
            )

            nombres_competiciones.append(nombre)

        except Exception:

            nombres_competiciones.append(
                f"Competicion_{indice + 1}"
            )

    print(
        "[INFO] Competiciones registradas:",
        len(nombres_competiciones)
    )

    # ==========================================
    # CONTADORES
    # ==========================================

    desplegadas = 0
    ya_abiertas = 0
    sin_respuesta = 0
    errores = 0
    recuperaciones = 0

    procesadas = set()

    # ==========================================
    # RECORRER COMPETICIONES
    # ==========================================

    for indice, nombre_guardado in enumerate(
        nombres_competiciones
    ):

        if indice in procesadas:
            continue

        print("\n" + "-" * 65)

        print(
            f"[{indice + 1}/{cantidad}] "
            f"Competición: {nombre_guardado}"
        )

        print("-" * 65)

        try:

            # Buscar nuevamente los bloques actuales.

            bloques = pagina.locator(selector)

            cantidad_actual = bloques.count()

            # Si desaparecieron los bloques, recuperar página.

            if cantidad_actual <= indice:

                print(
                    "[AVISO] Los bloques desaparecieron. "
                    "Intentando recuperar..."
                )

                recuperaciones += 1

                if not recuperar_pagina():

                    errores += 1

                    print(
                        "[AVISO] No se pudo recuperar. "
                        "Se continúa con la siguiente."
                    )

                    continue

                bloques = pagina.locator(selector)

                cantidad_actual = bloques.count()

            if cantidad_actual <= indice:

                print(
                    "[AVISO] No se encontró la competición "
                    "después de recargar."
                )

                errores += 1
                continue

            bloque = bloques.nth(indice)

            encabezado = bloque.locator(".rrc-74a")
            flecha = bloque.locator(".rrc-104")

            if encabezado.count() == 0 or flecha.count() == 0:

                print(
                    "[AVISO] No se encontró encabezado "
                    "o flecha."
                )

                errores += 1
                continue

            nombre_actual = encabezado.inner_text().strip()

            print("[INFO] Detectada:", nombre_actual)

            # Comprobar si ya está abierta.

            contenido = bloque.locator(
                ":scope > div:last-child"
            )

            altura = contenido.evaluate(
                "(el) => el.getBoundingClientRect().height"
            )

            if altura > 50:

                print(f"[ABIERTA] {nombre_actual}")

                ya_abiertas += 1
                procesadas.add(indice)

                continue

            # ==================================
            # INTENTAR DESPLEGAR
            # ==================================

            print(f"[CLIC] Desplegando: {nombre_actual}")

            cantidad_anterior = len(contenidos_upcoming)

            try:

                flecha.click(timeout=5000)

            except Exception as error:

                print(
                    "[AVISO] Error durante el clic:",
                    error
                )

                errores += 1

                # Recuperar y pasar a la siguiente.

                recuperaciones += 1

                recuperar_pagina()

                procesadas.add(indice)

                continue

            # ==================================
            # ESPERAR RESPUESTA DEL ENDPOINT
            # ==================================

            respuesta = esperar_nuevo_upcoming(
                pagina,
                cantidad_anterior,
                timeout=3
            )

            if respuesta:

                print(
                    f"[OK] Endpoint capturado: {nombre_actual}"
                )

                desplegadas += 1

                procesadas.add(indice)

                pagina.wait_for_timeout(300)

            else:

                print(
                    f"[AVISO] No se detectó nuevo endpoint: "
                    f"{nombre_actual}"
                )

                sin_respuesta += 1

                # ==================================
                # RECUPERACION AUTOMATICA
                # ==================================

                print(
                    "[RECUPERACION] Posible bloqueo "
                    "o reconstrucción del DOM."
                )

                recuperaciones += 1

                recuperado = recuperar_pagina()

                if recuperado:

                    print(
                        "[CONTINUANDO] Pasando a la "
                        "siguiente competición."
                    )

                else:

                    print(
                        "[AVISO] Recuperación fallida. "
                        "Se intentará continuar."
                    )

                procesadas.add(indice)

                continue

        except Exception as error:

            print(
                f"[ERROR] Competición {indice + 1}: {error}"
            )

            errores += 1

            # Si ocurre cualquier excepción,
            # intentar recuperar la página.

            recuperaciones += 1

            recuperar_pagina()

            procesadas.add(indice)

            continue

    # ==========================================
    # RESUMEN FINAL
    # ==========================================

    print("\n" + "=" * 65)
    print("RESUMEN DE COMPETICIONES")
    print("=" * 65)

    print("Competiciones detectadas:", cantidad)

    print("Ya estaban abiertas:", ya_abiertas)

    print("Desplegadas correctamente:", desplegadas)

    print("Sin nueva respuesta:", sin_respuesta)

    print("Errores:", errores)

    print("Recuperaciones de página:", recuperaciones)

    print(
        "Respuestas UPCOMING capturadas:",
        len(contenidos_upcoming)
    )

    print(
        "Competiciones recorridas:",
        len(procesadas)
    )

    print("\n[OK] Recorrido finalizado.")



def extraer_campos(bloque):

    campos = {}

    for coincidencia in re.finditer(
        r"(?:^|;)([A-Z0-9]+)=([^;|]*)",
        bloque
    ):

        clave = coincidencia.group(1)
        valor = coincidencia.group(2).strip()

        campos[clave] = valor

    return campos


# ==================================================
# EXTRAER PARTIDOS UPCOMING
# ==================================================

def extraer_partidos(texto):

    partidos = {}

    for bloque in texto.split("|"):

        bloque = bloque.strip()

        if not re.match(r"^(PA|EV);", bloque):
            continue

        datos = extraer_campos(bloque)

        fi = datos.get("FI", "").strip()

        if not fi.isdigit():
            continue

        nombre = (
            datos.get("FD")
            or datos.get("EX")
            or datos.get("NA")
            or "Sin nombre"
        )

        partidos[fi] = {
            "FI": fi,
            "Partido": nombre,
            "N2": datos.get("N2", ""),
            "N3": datos.get("N3", ""),
            "BC": datos.get("BC", "")
        }

    return list(partidos.values())


# ==================================================
# CONVERTIR CUOTA FRACCIONAL A DECIMAL
# ==================================================

def convertir_cuota(od):

    od = str(od).strip()

    if not od:
        return ""

    try:

        if "/" in od:

            numerador, denominador = od.split("/", 1)

            numerador = float(numerador)
            denominador = float(denominador)

            if denominador == 0:
                return od

            decimal = (numerador / denominador) + 1

        else:

            decimal = float(od)

        return round(decimal, 3)

    except (ValueError, ZeroDivisionError):

        return od


# ==================================================
# ANALIZAR DETALLE DEL PARTIDO
# ==================================================

def analizar_detalle(texto, fi_esperado, partido_upcoming):

    mercados = {
        "40": {
            "nombre": "Resultado del partido",
            "selecciones": [],
            "DO": "",
            "PD": ""
        },
        "10114": {
            "nombre": "Doble oportunidad",
            "selecciones": [],
            "DO": "",
            "PD": ""
        }
    }

    partido = {
        "FI": fi_esperado,
        "Partido": partido_upcoming.get("Partido", ""),
        "Local": "",
        "Visitante": "",
        "Fecha": partido_upcoming.get("BC", "")
    }

    mercado_actual = None

    selecciones_vistas = {
        "40": set(),
        "10114": set()
    }

    for bloque in texto.split("|"):

        bloque = bloque.strip()

        if not bloque:
            continue

        tipo = bloque.split(";", 1)[0]
        datos = extraer_campos(bloque)

        if tipo == "EV":

            fi_evento = datos.get("FI", "")

            if fi_evento == fi_esperado:

                partido["FI"] = fi_evento

                partido["Partido"] = (
                    datos.get("EX")
                    or partido["Partido"]
                )

                partido["Local"] = datos.get("N2", "")
                partido["Visitante"] = datos.get("N3", "")

                partido["Fecha"] = (
                    datos.get("BC")
                    or partido["Fecha"]
                )

            mercado_actual = None

        elif tipo == "MG":

            mercado_id = datos.get("ID", "")

            if mercado_id in MERCADOS_OBJETIVO:

                mercado_actual = mercado_id

                mercados[mercado_id]["DO"] = datos.get("DO", "")
                mercados[mercado_id]["PD"] = datos.get("PD", "")

            else:

                mercado_actual = None

        elif tipo == "PA" and mercado_actual:

            seleccion_id = datos.get("ID", "")

            clave = (
                seleccion_id
                or (
                    datos.get("NA", ""),
                    datos.get("N2", ""),
                    datos.get("OD", "")
                )
            )

            if clave in selecciones_vistas[mercado_actual]:
                continue

            selecciones_vistas[mercado_actual].add(clave)

            seleccion = {
                "ID": seleccion_id,
                "NA": datos.get("NA", ""),
                "N2": datos.get("N2", ""),
                "OD": datos.get("OD", ""),
                "Cuota": convertir_cuota(datos.get("OD", "")),
                "SU": datos.get("SU", "")
            }

            mercados[mercado_actual]["selecciones"].append(
                seleccion
            )

    if not partido["Partido"]:

        local = partido["Local"]
        visitante = partido["Visitante"]

        if local and visitante:
            partido["Partido"] = f"{local} v {visitante}"

    return partido, mercados


# ==================================================
# CONSTRUIR FILAS DEL CSV
# ==================================================

def construir_filas(partido, mercados):

    filas = []

    for mercado_id, mercado in mercados.items():

        for seleccion in mercado["selecciones"]:

            estado = (
                "Suspendida"
                if seleccion["SU"] == "1"
                else "Disponible"
                if seleccion["SU"] == "0"
                else "Desconocido"
            )

            filas.append({

                "FI": partido["FI"],
                "Partido": partido["Partido"],
                "Local": partido["Local"],
                "Visitante": partido["Visitante"],
                "Fecha": partido["Fecha"],

                "Mercado": mercado["nombre"],
                "ID_Mercado": mercado_id,

                "Seleccion": seleccion["NA"],
                "Etiqueta": seleccion["N2"],

                "Cuota_original": seleccion["OD"],
                "Cuota_decimal": seleccion["Cuota"],

                "Estado": estado

            })

    if not filas:

        filas.append({

            "FI": partido["FI"],
            "Partido": partido["Partido"],
            "Local": partido["Local"],
            "Visitante": partido["Visitante"],
            "Fecha": partido["Fecha"],

            "Mercado": "Sin cuotas disponibles",
            "ID_Mercado": "",

            "Seleccion": "",
            "Etiqueta": "",

            "Cuota_original": "",
            "Cuota_decimal": "",

            "Estado": ""

        })

    return filas


# ==================================================
# FIN DE LA PARTE 1
# ==================================================

# ==================================================
# PROGRAMA PRINCIPAL
# ==================================================

def main():

    global contenido_upcoming
    global contenidos_upcoming
    global contenido_detalle
    global url_detalle
    global fi_actual

    print("=" * 65)
    print("BET365 - EXTRACCION AUTOMATICA DE PARTIDOS Y CUOTAS")
    print("=" * 65)

    filas_finales = []
    partidos_fallidos = []

    with sync_playwright() as p:

        argumentos = {
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled"
            ]
        }

        if BRAVE:
            argumentos["executable_path"] = BRAVE

        navegador = p.chromium.launch(**argumentos)

        contexto = navegador.new_context(
            viewport={"width": 1366, "height": 768}
        )

        pagina = contexto.new_page()

        pagina.on("response", escuchar_respuestas)

        try:

            # ======================================
            # PASO 1: CAPTURAR UPCOMING
            # ======================================

            print("\n[1] Abriendo Bet365...")

            contenido_upcoming = None
            contenidos_upcoming = []

            try:

                pagina.goto(
                    URL_UPCOMING,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

            except Exception as error:
                print("[AVISO]", error)

            encontrado = esperar_respuesta(
                pagina,
                "upcoming",
                TIEMPO_UPCOMING
            )

            if not encontrado:

                print("[ERROR] No se recibió respuesta upcoming.")
                return

            contenido_anterior = contenido_upcoming

            # ======================================
            # PASO 2: ACTUALIZAR UPCOMING
            # ======================================

            print("\n[2] Actualizando lista de partidos...")

            contenido_upcoming = None

            try:

                pagina.reload(
                    wait_until="domcontentloaded",
                    timeout=60000
                )

            except Exception as error:
                print("[AVISO]", error)

            actualizado = esperar_respuesta(
                pagina,
                "upcoming",
                TIEMPO_UPCOMING
            )

            if actualizado:

                print("[OK] Lista actualizada.")

            else:

                contenido_upcoming = contenido_anterior

                print("[AVISO] Se utilizará la primera respuesta.")

            # ======================================
            # PASO 3: DESPLEGAR COMPETICIONES
            # ======================================

            print("\n[3] Buscando competiciones cerradas...")

            desplegar_competiciones(pagina)

            # ======================================
            # PASO 4: UNIFICAR TODOS LOS UPCOMING
            # ======================================

            print("\n" + "=" * 65)
            print("UNIFICANDO PARTIDOS DE TODAS LAS COMPETICIONES")
            print("=" * 65)

            partidos_unificados = {}

            # Procesar todas las respuestas capturadas.

            for respuesta in contenidos_upcoming:

                partidos_respuesta = extraer_partidos(respuesta)

                for partido in partidos_respuesta:

                    fi = partido["FI"]

                    # Evitar duplicados por FI.
                    partidos_unificados[fi] = partido

            # Respaldo por si alguna respuesta no quedó en la lista.

            if not partidos_unificados and contenido_upcoming:

                for partido in extraer_partidos(contenido_upcoming):

                    partidos_unificados[partido["FI"]] = partido

            partidos = list(partidos_unificados.values())

            print(
                "[OK] Respuestas UPCOMING:",
                len(contenidos_upcoming)
            )

            print(
                "[OK] Partidos únicos encontrados:",
                len(partidos)
            )

            if not partidos:

                print("[ERROR] No hay partidos para procesar.")
                return

            # ======================================
            # PASO 5: RECORRER TODOS LOS PARTIDOS
            # ======================================

            total = len(partidos)

            print("\n")
            print("=" * 65)
            print("INICIANDO RECORRIDO DE PARTIDOS")
            print("=" * 65)

            for indice, partido_upcoming in enumerate(partidos, 1):

                fi = partido_upcoming["FI"]

                url_partido = (
                    "https://www.bet365.pe/#/AC/B1/C1/"
                    f"D8/E{fi}/F3/I1/"
                )

                print("\n" + "-" * 65)
                print(f"[{indice}/{total}] Consultando FI: {fi}")
                print("-" * 65)

                fi_actual = fi
                contenido_detalle = None
                url_detalle = None

                # PRIMER INTENTO

                try:

                    pagina.goto(
                        url_partido,
                        wait_until="domcontentloaded",
                        timeout=20000
                    )

                except Exception as error:

                    print("[AVISO] Navegación:", error)

                encontrado = esperar_respuesta(
                    pagina,
                    "detalle",
                    timeout=TIEMPO_REINTENTO
                )

                # SEGUNDO INTENTO: REFRESH

                if not encontrado:

                    print("[AVISO] Sin respuesta válida. Reintentando...")

                    pagina.wait_for_timeout(500)

                    contenido_detalle = None
                    url_detalle = None

                    try:

                        pagina.reload(
                            wait_until="domcontentloaded",
                            timeout=20000
                        )

                    except Exception as error:

                        print("[AVISO] Error al refrescar:", error)

                    encontrado = esperar_respuesta(
                        pagina,
                        "detalle",
                        timeout=TIEMPO_REINTENTO
                    )

                # SI LOS DOS INTENTOS FALLARON

                if not encontrado:

                    print(
                        f"[ERROR] FI {fi} no respondió "
                        "después del reintento."
                    )

                    partidos_fallidos.append({
                        "FI": fi,
                        "Partido": partido_upcoming.get("Partido", ""),
                        "Motivo": "Sin respuesta válida después de dos intentos"
                    })

                    continue

                # ANALIZAR DETALLE

                print("[OK] Respuesta válida recibida.")

                partido, mercados = analizar_detalle(
                    contenido_detalle,
                    fi,
                    partido_upcoming
                )

                filas = construir_filas(
                    partido,
                    mercados
                )

                filas_finales.extend(filas)

                # RESUMEN DEL PARTIDO

                print("Partido:", partido["Partido"])

                print(
                    "Equipos:",
                    partido["Local"],
                    "vs",
                    partido["Visitante"]
                )

                for mercado_id, mercado in mercados.items():

                    print(
                        f"{mercado['nombre']}: "
                        f"{len(mercado['selecciones'])} selecciones"
                    )

                print("Filas agregadas:", len(filas))

            # ======================================
            # PASO 6: GUARDAR PARTIDOS FALLIDOS
            # ======================================

            print("\n" + "=" * 65)
            print("GUARDANDO PARTIDOS FALLIDOS")
            print("=" * 65)

            if partidos_fallidos:

                with open(
                    "partidos_fallidos.csv",
                    "w",
                    newline="",
                    encoding="utf-8-sig"
                ) as archivo:

                    columnas = ["FI", "Partido", "Motivo"]

                    escritor = csv.DictWriter(
                        archivo,
                        fieldnames=columnas
                    )

                    escritor.writeheader()
                    escritor.writerows(partidos_fallidos)

                print(
                    "[AVISO] Partidos fallidos:",
                    len(partidos_fallidos)
                )

                print("Archivo: partidos_fallidos.csv")

            else:

                print("[OK] Todos los partidos respondieron correctamente.")

                # Eliminar archivo anterior si ya no hay fallidos.
                archivo_fallidos = Path("partidos_fallidos.csv")

                if archivo_fallidos.exists():
                    archivo_fallidos.unlink()

            # ======================================
            # PASO 7: GENERAR CSV FINAL
            # ======================================

            print("\n")
            print("=" * 65)
            print("GENERANDO ARCHIVO FINAL")
            print("=" * 65)

            columnas = [
                "FI",
                "Partido",
                "Local",
                "Visitante",
                "Fecha",
                "Mercado",
                "ID_Mercado",
                "Seleccion",
                "Etiqueta",
                "Cuota_original",
                "Cuota_decimal",
                "Estado"
            ]

            with ARCHIVO_SALIDA.open(
                "w",
                newline="",
                encoding="utf-8-sig"
            ) as archivo:

                escritor = csv.DictWriter(
                    archivo,
                    fieldnames=columnas
                )

                escritor.writeheader()
                escritor.writerows(filas_finales)

            # ======================================
            # RESUMEN FINAL
            # ======================================

            print("\nPROCESO TERMINADO")
            print("-" * 65)

            print("Competiciones/respuestas capturadas:",
                  len(contenidos_upcoming))

            print("Partidos únicos encontrados:", total)

            print("Filas generadas:", len(filas_finales))

            print("Partidos fallidos:", len(partidos_fallidos))

            print(
                "Archivo final:",
                ARCHIVO_SALIDA.resolve()
            )

            print("\n[OK] Extracción completada.")

        finally:

            fi_actual = None
            navegador.close()


# ==================================================
# EJECUCION
# ==================================================

if __name__ == "__main__":
    main()
