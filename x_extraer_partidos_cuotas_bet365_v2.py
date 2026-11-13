import os
import re
import json
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

ARCHIVO_JSON_SALIDA = Path("cuotas_partidos.json")

TIEMPO_UPCOMING = 20
TIEMPO_DETALLE = 15
TIEMPO_REINTENTO = 2

MERCADOS_OBJETIVO = {
    "40": "Resultado del partido",
    "10114": "Doble oportunidad"
}


# ==================================================
# EXPRESIONES REGULARES PRECOMPILADAS
# ==================================================
REGEX_CAMPOS = re.compile(r"(?:^|;)([A-Z0-9]+)=([^;|]*)")


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
# ESPERAR RESPUESTA (POLLING ADAPTATIVO)
# ==================================================

def esperar_respuesta(pagina, tipo, timeout=5):

    global contenido_upcoming
    global contenido_detalle

    inicio = time.monotonic()
    intervalo = 0.05

    while time.monotonic() - inicio < timeout:
        if tipo == "upcoming":
            if contenido_upcoming and len(contenido_upcoming) > 1000:
                return True
        elif tipo == "detalle":
            if contenido_detalle and len(contenido_detalle) > 1000:
                if "|EV;" in contenido_detalle and "|MG;" in contenido_detalle:
                    return True

        pagina.wait_for_timeout(int(intervalo * 1000))
        if intervalo < 0.2:
            intervalo += 0.02

    return False


def esperar_nuevo_upcoming(pagina, cantidad_anterior, timeout=3.0):

    inicio = time.monotonic()
    intervalo = 0.05

    while time.monotonic() - inicio < timeout:
        if len(contenidos_upcoming) > cantidad_anterior:
            return True
        pagina.wait_for_timeout(int(intervalo * 1000))
        if intervalo < 0.2:
            intervalo += 0.02

    return False


# ==================================================
# DETECTAR Y DESPLEGAR COMPETICIONES
# ==================================================

def desplegar_competiciones(pagina):

    global contenido_upcoming

    print("\n" + "=" * 65)
    print("DETECTANDO Y DESPLEGANDO COMPETICIONES")
    print("=" * 65)

    selector = ".rrc-d5"

    def recuperar_pagina():
        global contenido_upcoming
        print("\n[RECUPERACION] La página se congeló o falló. Recargando Bet365...")
        try:
            contenido_upcoming = None
            pagina.reload(wait_until="domcontentloaded", timeout=30000)
            inicio = time.monotonic()
            intervalo = 0.05
            while time.monotonic() - inicio < 15:
                if pagina.locator(selector).count() > 0:
                    break
                pagina.wait_for_timeout(int(intervalo * 1000))
                if intervalo < 0.2:
                    intervalo += 0.02
            esperar_respuesta(pagina, "upcoming", timeout=8)
            cantidad_actual = pagina.locator(selector).count()
            if cantidad_actual > 0:
                print(f"[RECUPERACION OK] Competiciones: {cantidad_actual}")
                return True
            return False
        except Exception as error:
            print("[ERROR RECUPERACION]", error)
            return False

    inicio = time.monotonic()
    cantidad = 0
    intervalo = 0.05

    while time.monotonic() - inicio < 10:
        cantidad = pagina.locator(selector).count()
        if cantidad > 0:
            break
        pagina.wait_for_timeout(int(intervalo * 1000))
        if intervalo < 0.2:
            intervalo += 0.02

    print(f"[INFO] Competiciones detectadas: {cantidad}")
    if cantidad == 0:
        return

    nombres_competiciones = []
    bloques = pagina.locator(selector)

    for indice in range(cantidad):
        try:
            nombre = bloques.nth(indice).locator(".rrc-74a").inner_text(timeout=3000).strip()
            nombres_competiciones.append(nombre)
        except Exception:
            nombres_competiciones.append(f"Competicion_{indice + 1}")

    desplegadas = 0
    ya_abiertas = 0
    sin_respuesta = 0
    errores = 0
    recuperaciones = 0
    procesadas = set()

    for indice, nombre_guardado in enumerate(nombres_competiciones):
        if indice in procesadas:
            continue

        print(f"\n[{indice + 1}/{cantidad}] Competición: {nombre_guardado}")
        try:
            bloques = pagina.locator(selector)
            cantidad_actual = bloques.count()

            if cantidad_actual <= indice:
                recuperaciones += 1
                if not recuperar_pagina():
                    errores += 1
                    continue
                bloques = pagina.locator(selector)
                cantidad_actual = bloques.count()

            if cantidad_actual <= indice:
                errores += 1
                continue

            bloque = bloques.nth(indice)
            encabezado = bloque.locator(".rrc-74a")
            flecha = bloque.locator(".rrc-104")

            if encabezado.count() == 0 or flecha.count() == 0:
                errores += 1
                continue

            contenido = bloque.locator(":scope > div:last-child")
            altura = contenido.evaluate("(el) => el.getBoundingClientRect().height")

            if altura > 50:
                ya_abiertas += 1
                procesadas.add(indice)
                continue

            cantidad_anterior = len(contenidos_upcoming)
            try:
                flecha.click(timeout=5000)
            except Exception:
                errores += 1
                recuperaciones += 1
                recuperar_pagina()
                procesadas.add(indice)
                continue

            respuesta = esperar_nuevo_upcoming(pagina, cantidad_anterior, timeout=3.0)
            if respuesta:
                desplegadas += 1
                procesadas.add(indice)
                pagina.wait_for_timeout(200)
            else:
                sin_respuesta += 1
                recuperaciones += 1
                recuperar_pagina()
                procesadas.add(indice)
                continue

        except Exception:
            errores += 1
            recuperaciones += 1
            recuperar_pagina()
            procesadas.add(indice)
            continue


def extraer_campos(bloque):
    campos = {}
    for coincidencia in REGEX_CAMPOS.finditer(bloque):
        clave = coincidencia.group(1)
        valor = coincidencia.group(2).strip()
        campos[clave] = valor
    return campos


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
        nombre = datos.get("FD") or datos.get("EX") or datos.get("NA") or "Sin nombre"
        partidos[fi] = {
            "FI": fi,
            "Partido": nombre,
            "N2": datos.get("N2", ""),
            "N3": datos.get("N3", ""),
            "BC": datos.get("BC", "")
        }
    return list(partidos.values())


def convertir_cuota(od):
    od = str(od).strip()
    if not od:
        return None
    try:
        if "/" in od:
            numerador, denominador = od.split("/", 1)
            decimal = (float(numerador) / float(denominador)) + 1
        else:
            decimal = float(od)
        return round(decimal, 3)
    except (ValueError, ZeroDivisionError):
        return od


# ==================================================
# ANALIZAR DETALLE Y ADAPTAR A FORMATO ESTRUCTURADO
# ==================================================

def analizar_detalle(texto, fi_esperado, partido_upcoming):

    partido_info = {
        "FI": fi_esperado,
        "partido": partido_upcoming.get("Partido", ""),
        "local": "",
        "visitante": "",
        "fecha": partido_upcoming.get("BC", ""),
        "resultado_partido": {
            "cuota_local": None,
            "cuota_empate": None,
            "cuota_visitante": None,
            "estado": "No disponible"
        },
        "doble_oportunidad": []
    }

    mercado_actual = None

    for bloque in texto.split("|"):
        bloque = bloque.strip()
        if not bloque:
            continue

        tipo = bloque.split(";", 1)[0]
        datos = extraer_campos(bloque)

        if tipo == "EV":
            fi_evento = datos.get("FI", "")
            if fi_evento == fi_esperado:
                partido_info["local"] = datos.get("N2", "")
                partido_info["visitante"] = datos.get("N3", "")
                partido_info["fecha"] = datos.get("BC") or partido_info["fecha"]
                if datos.get("EX"):
                    partido_info["partido"] = datos.get("EX")
            mercado_actual = None

        elif tipo == "MG":
            mercado_id = datos.get("ID", "")
            if mercado_id in MERCADOS_OBJETIVO:
                mercado_actual = mercado_id
            else:
                mercado_actual = None

        elif tipo == "PA" and mercado_actual:
            od = datos.get("OD", "")
            cuota_dec = convertir_cuota(od)
            estado = "Suspendida" if datos.get("SU") == "1" else "Disponible"

            # Mercado 40: Resultado del Partido (1X2)
            if mercado_actual == "40":
                etiqueta = datos.get("N2", "") # 1, X, 2
                if etiqueta == "1":
                    partido_info["resultado_partido"]["cuota_local"] = cuota_dec
                    partido_info["resultado_partido"]["estado"] = estado
                elif etiqueta == "X":
                    partido_info["resultado_partido"]["cuota_empate"] = cuota_dec
                elif etiqueta == "2":
                    partido_info["resultado_partido"]["cuota_visitante"] = cuota_dec

            # Mercado 10114: Doble Oportunidad
            elif mercado_actual == "10114":
                partido_info["doble_oportunidad"].append({
                    "seleccion": datos.get("NA", ""),
                    "etiqueta": datos.get("N2", ""),
                    "cuota_decimal": cuota_dec,
                    "estado": estado
                })

    if not partido_info["partido"] and partido_info["local"] and partido_info["visitante"]:
        partido_info["partido"] = f"{partido_info['local']} v {partido_info['visitante']}"

    return partido_info


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
    print("BET365 - EXTRACCION A JSON ESTRUCTURADO")
    print("=" * 65)

    tiempo_inicio_global = time.monotonic()
    partidos_json_final = []
    partidos_fallidos = []

    with sync_playwright() as p:
        argumentos = {
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"]
        }

        if BRAVE:
            argumentos["executable_path"] = BRAVE

        navegador = p.chromium.launch(**argumentos)
        contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
        pagina = contexto.new_page()
        pagina.on("response", escuchar_respuestas)

        try:
            print("\n[1] Abriendo Bet365...")
            contenido_upcoming = None
            contenidos_upcoming = []

            try:
                pagina.goto(URL_UPCOMING, wait_until="domcontentloaded", timeout=60000)
            except Exception as error:
                print("[AVISO]", error)

            if not esperar_respuesta(pagina, "upcoming", TIEMPO_UPCOMING):
                print("[ERROR] No se recibió respuesta upcoming.")
                return

            contenido_anterior = contenido_upcoming

            print("\n[2] Actualizando lista de partidos...")
            contenido_upcoming = None
            try:
                pagina.reload(wait_until="domcontentloaded", timeout=60000)
            except Exception as error:
                print("[AVISO]", error)

            if not esperar_respuesta(pagina, "upcoming", TIEMPO_UPCOMING):
                contenido_upcoming = contenido_anterior

            print("\n[3] Buscando competiciones...")
            desplegar_competiciones(pagina)

            print("\n" + "=" * 65)
            print("UNIFICANDO PARTIDOS")
            print("=" * 65)

            partidos_unificados = {}
            for respuesta in contenidos_upcoming:
                for partido in extraer_partidos(respuesta):
                    partidos_unificados[partido["FI"]] = partido

            if not partidos_unificados and contenido_upcoming:
                for partido in extraer_partidos(contenido_upcoming):
                    partidos_unificados[partido["FI"]] = partido

            partidos = list(partidos_unificados.values())
            total = len(partidos)
            print(f"[OK] Partidos únicos encontrados: {total}")

            if not partidos:
                print("[ERROR] No hay partidos para procesar.")
                return

            print("\n" + "=" * 65)
            print("INICIANDO RECORRIDO Y EXTRACCIÓN DE CUOTAS")
            print("=" * 65)

            for indice, partido_upcoming in enumerate(partidos, 1):
                fi = partido_upcoming["FI"]
                url_partido = f"https://www.bet365.pe/#/AC/B1/C1/D8/E{fi}/F3/I1/"

                print(f"\n[{indice}/{total}] Consultando FI: {fi} ({partido_upcoming.get('Partido')})")

                fi_actual = fi
                contenido_detalle = None
                url_detalle = None

                try:
                    pagina.goto(url_partido, wait_until="domcontentloaded", timeout=20000)
                except Exception as error:
                    print("[AVISO] Navegación:", error)

                encontrado = esperar_respuesta(pagina, "detalle", timeout=TIEMPO_REINTENTO)

                if not encontrado:
                    print(f"[AVISO] FI {fi} sin respuesta a la primera. Saltando...")
                    partidos_fallidos.append({
                        "FI": fi,
                        "Partido": partido_upcoming.get("Partido", "")
                    })
                    continue

                print("[OK] Datos de cupones recibidos.")
                datos_partido = analizar_detalle(contenido_detalle, fi, partido_upcoming)
                partidos_json_final.append(datos_partido)

                # Imprimir formato solicitado en consola para validación visual rápida
                res_partido = datos_partido["resultado_partido"]
                print(f"👉 {datos_partido['partido']}")
                print(f"   RESULTADO PARTIDO -> [Local: {res_partido['cuota_local']} | Empate: {res_partido['cuota_empate']} | Visitante: {res_partido['cuota_visitante']}]")

            # Guardar archivo JSON estructurado
            with ARCHIVO_JSON_SALIDA.open("w", encoding="utf-8") as archivo:
                json.dump(partidos_json_final, archivo, indent=4, ensure_ascii=False)

            tiempo_fin_global = time.monotonic()
            tiempo_total = tiempo_fin_global - tiempo_inicio_global
            minutos = int(tiempo_total // 60)
            segundos = int(tiempo_total % 60)

            print("\nPROCESO TERMINADO")
            print("-" * 65)
            print(f"Partidos procesados correctamente: {len(partidos_json_final)}")
            print(f"Partidos fallidos: {len(partidos_fallidos)}")
            print(f"Archivo JSON generado: {ARCHIVO_JSON_SALIDA.resolve()}")
            print(f"\n⏱️ [TIEMPO TOTAL]: {minutos}m {segundos}s ({tiempo_total:.2f} segundos)")

        finally:
            fi_actual = None
            navegador.close()


if __name__ == "__main__":
    main()