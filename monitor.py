#!/usr/bin/env python3
"""
Monitor de citas para la devolución del IVA de vehículos eléctricos o híbridos.

Trabaja en TU Google Chrome (tu perfil y tus sesiones): controla una pestaña con
AppleScript, recorre Agendar cita > Persona Natural > Videoatención > Devoluciones
y revisa el campo "Trámite". Solo avisa si aparece el trámite de vehículos
eléctricos o híbridos para la ciudad elegida. En ese caso elige esa opción, da clic
en "Siguiente" y, si la plataforma pasa al paso 2 (sede, fecha y hora), te avisa y se
detiene. Si la plataforma responde que ya no hay citas, no avisa y sigue vigilando.
No le quita el foco a la app que estés usando, salvo que pidas --enfocar. Los datos
personales y el captcha los completas tú.

Requisitos (una sola vez):
  1. Chrome > Visualización > Opciones para desarrolladores > Permitir JavaScript desde Apple Events.
  2. Aceptar el permiso de macOS para que la Terminal controle Google Chrome.

Uso:
    python3 monitor.py                          # Bogotá, revisa cada ~60-80 s
    python3 monitor.py --ciudad Medellín Cali   # una o varias ciudades
    python3 monitor.py --una-vez                # una sola revisión (prueba)
    python3 monitor.py --enfocar                # al encontrar la cita, traer Chrome al frente
    python3 monitor.py --probar-notificacion    # prueba el aviso al teléfono
"""
import argparse
import json
import os
import random
import secrets
import subprocess
import sys
import time
import unicodedata
from datetime import datetime

URL = "https://agendamiento.dian.gov.co/"
CIUDADES = ["Bogotá", "Medellín", "Cali", "Bucaramanga"]
TRAMITE = ["vehiculos electricos", "hibridos"]  # palabras del trámite, sin tildes

INTERVALO_MIN = 60   # s; fijo: revisar más seguido puede hacer que la plataforma bloquee las revisiones
TIMEOUT_CICLO = 120  # s; la plataforma a veces tarda bastante
SONDEO = 0.4         # s entre consultas a la pestaña
TIMEOUT_OSA = 20     # s máximos que esperamos a que Chrome responda una orden
TIMEOUT_AVANCE = 30  # s máximos para elegir el trámite y pasar al paso 2
ESPERA_BOTON = 5     # s máximos para que se habilite "Siguiente" tras elegir el trámite
ESPERA_PASO_DOS = 2  # s que se espera en el paso 2 por si aparece el aviso de "sin citas"

ARCHIVO_TOPIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ntfy_topic.txt")


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def normalizar(texto):
    """Minúsculas y sin tildes, para comparar 'Bogotá' con 'BOGOTA', 'bogota', etc."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def es_objetivo(opcion, ciudades):
    o = normalizar(opcion)
    return all(p in o for p in TRAMITE) and any(normalizar(c) in o for c in ciudades)


# --- Avisos ------------------------------------------------------------------

def obtener_topic_ntfy():
    """Tema privado de ntfy (nombre aleatorio difícil de adivinar), creado una sola vez."""
    if not os.path.exists(ARCHIVO_TOPIC):
        with open(ARCHIVO_TOPIC, "w") as f:
            f.write("citas-" + secrets.token_hex(8))
    with open(ARCHIVO_TOPIC) as f:
        return f.read().strip()


def notificar_telefono(titulo, mensaje):
    """Push al teléfono vía ntfy.sh (app gratuita ntfy en iOS/Android, sin cuenta)."""
    r = subprocess.run(
        ["curl", "-s", "-m", "20", "-o", "/dev/null", "-w", "%{http_code}",
         "-H", f"Title: {titulo}", "-H", "Priority: urgent", "-H", "Tags: rotating_light",
         "-H", f"Click: {URL}", "-d", mensaje, f"https://ntfy.sh/{obtener_topic_ntfy()}"],
        capture_output=True, text=True)
    if r.stdout.strip() == "200":
        log("Notificación enviada al teléfono (ntfy).")
    else:
        log(f"No se pudo enviar la notificación al teléfono (HTTP {r.stdout.strip() or 'error'}).")


def notificar(titulo, mensaje):
    """Notificación al teléfono + notificación de macOS + sonido + voz."""
    notificar_telefono(titulo, mensaje)
    t = titulo.replace('"', "'")
    m = mensaje.replace('"', "'")
    subprocess.run(["osascript", "-e", f'display notification "{m}" with title "{t}" sound name "Glass"'])
    subprocess.Popen(["say", "Hay citas disponibles"], stderr=subprocess.DEVNULL)
    for _ in range(3):
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        time.sleep(0.6)


# --- Control de Chrome con AppleScript -----------------------------------------

# JavaScript que se ejecuta en la pestaña en cada sondeo. Es síncrono y devuelve
# un texto con el estado; hace como mucho UN clic por llamada.
JS_PASO = r"""
(function () {
  if (document.readyState !== 'complete') return 'CARGANDO';
  var vis = function (el) {
    return !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  var P = 'div[nombre="PasoUno"] ';
  var modal = document.querySelector('div[nombre="ModalError"] div[nombre="txtInfoAdicional"]');
  if (vis(modal) && modal.textContent.indexOf('No se encontraron especialidades') >= 0) return 'SIN_CITAS';
  var sel = document.querySelector(P + 'div[nombre="Servicios"] select');
  if (vis(sel)) {
    var ops = Array.prototype.map.call(sel.options, function (o) { return o.text.trim(); }).filter(Boolean);
    if (ops.length) return 'TRAMITE\n' + ops.join('\n');
  }
  var hecho = window.__monitorCitas || (window.__monitorCitas = {});
  var pasos = [
    ['devoluciones', P + 'div[nombre="Categorias"] .boton', 'Devoluciones'],
    ['videoatencion', P + 'div[nombre="TipoAtencion"] .boton', 'Videoatención'],
    ['natural', P + 'div[nombre="TipoPersona"] .boton[llave="1"]', null],
    ['agendar', 'div[nombre="Inicio"] .boton', 'Agendar cita']
  ];
  for (var i = 0; i < pasos.length; i++) {
    var k = pasos[i][0];
    if (hecho[k]) continue;
    var b = Array.prototype.find.call(document.querySelectorAll(pasos[i][1]), function (x) {
      return vis(x) && (!pasos[i][2] || x.textContent.indexOf(pasos[i][2]) >= 0);
    });
    if (b) { b.click(); hecho[k] = 1; return 'CLIC ' + k; }
  }
  return 'ESPERANDO';
})()
"""

# JavaScript que elige el trámite objetivo en "Trámite" y da clic en "Siguiente".
# Se ejecuta en cada sondeo y hace como mucho UNA acción por llamada. __OBJETIVO__ se
# reemplaza por el texto exacto de la opción. No llena datos personales.
JS_AVANZAR = r"""
(function (objetivo) {
  var vis = function (el) {
    return !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  var modales = ['ModalSinCitas', 'ModalError'];
  for (var i = 0; i < modales.length; i++) {
    var m = document.querySelector('div[nombre="' + modales[i] + '"]');
    if (vis(m)) {
      var txt = Array.prototype.map.call(m.querySelectorAll('div[nombre="txtTituloModal"], div[nombre="txtInfoAdicional"]'),
        function (x) { return x.textContent.trim(); }).filter(Boolean).join(' ');
      return 'SIN_CUPO\n' + txt.replace(/\s+/g, ' ');
    }
  }
  if (vis(document.querySelector('div[nombre="PasoDos"]'))) return 'PASO_DOS';
  var P = 'div[nombre="PasoUno"] ';
  var est = window.__monitorAvance || (window.__monitorAvance = {});
  if (!est.elegido) {
    var sel = document.querySelector(P + 'div[nombre="Servicios"] select');
    if (!vis(sel)) return 'SIN_SELECT';
    var op = Array.prototype.find.call(sel.options, function (o) { return o.text.trim() === objetivo; });
    if (!op) return 'SIN_OPCION';
    sel.selectedIndex = op.index;
    sel.dispatchEvent(new Event('input', {bubbles: true}));
    sel.dispatchEvent(new Event('change', {bubbles: true}));
    est.elegido = 1;
    return 'ELEGIDO';
  }
  if (!est.siguiente) {
    var b = document.querySelector(P + 'div[nombre="btnSiguiente"]');
    if (vis(b)) { b.click(); est.siguiente = 1; return 'CLIC siguiente'; }
    return 'ESPERANDO_BOTON';
  }
  return 'ESPERANDO';
})(__OBJETIVO__)
"""

JS_RESALTAR = r"""
(function () {
  var p2 = document.querySelector('div[nombre="PasoDos"]');
  if (p2 && p2.getClientRects().length > 0) {
    window.scrollTo(0, 0);
  } else {
    var sel = document.querySelector('div[nombre="PasoUno"] div[nombre="Servicios"] select');
    if (sel) { sel.scrollIntoView({block: 'center'}); sel.style.outline = '4px solid #16a34a'; sel.focus(); }
  }
  document.title = '¡CITA DISPONIBLE!';
  return 'ok';
})()
"""


class ErrorChrome(Exception):
    pass


def osa(script, *args):
    """Ejecuta AppleScript con argumentos (sin problemas de comillas) y devuelve stdout."""
    cmd = ["osascript"]
    for linea in script.strip().splitlines():
        cmd += ["-e", linea]
    try:
        r = subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=TIMEOUT_OSA)
    except subprocess.TimeoutExpired:
        raise ErrorChrome(f"Chrome no respondió en {TIMEOUT_OSA}s (pestaña congelada o diálogo abierto)")
    if r.returncode != 0:
        err = r.stderr.strip()
        if "JavaScript" in err and ("Apple Events" in err or "AppleScript" in err):
            raise ErrorChrome("Chrome no permite JavaScript desde Apple Events. Actívalo en "
                              "Chrome > Visualización > Opciones para desarrolladores > Permitir JavaScript desde Apple Events.")
        if "-1743" in err or "Not authorized" in err:
            raise ErrorChrome("macOS no ha autorizado controlar Google Chrome. Revisa "
                              "Ajustes del Sistema > Privacidad y seguridad > Automatización.")
        raise ErrorChrome(err or "error desconocido de AppleScript")
    return r.stdout.strip()


def pestana_perdida(e):
    """¿El error indica que la ventana o pestaña del monitor ya no existe?

    Se revisan los códigos de error de AppleScript, que no dependen del idioma de macOS:
    -1728 (no se puede obtener), -1719 (índice no válido), -10006 (no se puede ajustar).
    Pasa, por ejemplo, cuando Chrome se reinicia: las ventanas restauradas tienen otros ids.
    """
    return any(c in str(e) for c in ("(-1728)", "(-1719)", "(-10006)"))


def pestana_dedicada():
    """Busca una pestaña de la plataforma en tu Chrome; si no hay, abre una ventana nueva."""
    salida = osa("""
on run argv
  tell application "Google Chrome"
    repeat with w in windows
      repeat with t in tabs of w
        if (URL of t) starts with (item 1 of argv) then return (id of w as text) & " " & (id of t as text)
      end repeat
    end repeat
    set w to make new window
    set URL of active tab of w to (item 1 of argv)
    return (id of w as text) & " " & (id of active tab of w as text)
  end tell
end run
""", URL)
    w, t = salida.split()
    return w, t


def js(w, t, codigo):
    return osa("""
on run argv
  tell application "Google Chrome"
    return execute (tab id (item 2 of argv as integer) of window id (item 1 of argv as integer)) javascript (item 3 of argv)
  end tell
end run
""", w, t, codigo)


def navegar(w, t):
    """Recarga el sitio en la pestaña sin quitarle el foco a la app que estás usando.

    Cambiar la URL con AppleScript ("set URL") trae Chrome al frente; navegar con
    JavaScript dentro de la pestaña no. Si la pestaña no acepta JavaScript (p. ej.
    una página interna de Chrome), se usa AppleScript como respaldo.
    """
    try:
        js(w, t, "location.replace(" + repr(URL) + "); 'ok'")
        return
    except ErrorChrome:
        pass
    osa("""
on run argv
  tell application "Google Chrome"
    set URL of (tab id (item 2 of argv as integer) of window id (item 1 of argv as integer)) to (item 3 of argv)
  end tell
end run
""", w, t, URL)


def mostrar_pestana(w, t, enfocar=False):
    """Deja visible la pestaña del monitor en su ventana. Solo con enfocar=True trae
    Chrome al frente (eso le quita el foco a la app que estés usando)."""
    osa("""
on run argv
  tell application "Google Chrome"
    set w to window id (item 1 of argv as integer)
    set i to 0
    repeat with t in tabs of w
      set i to i + 1
      if (id of t as text) = (item 2 of argv) then set active tab index of w to i
    end repeat
    if (item 3 of argv) is "si" then
      set index of w to 1
      activate
    end if
  end tell
end run
""", w, t, "si" if enfocar else "no")


def revisar(w, t, ciudades):
    """Un ciclo completo. Devuelve (estado, opciones) con estado sin_citas | objetivo | otras."""
    navegar(w, t)
    time.sleep(1.5)  # deja que empiece la carga nueva antes del primer sondeo
    r = ""
    limite = time.time() + TIMEOUT_CICLO
    while time.time() < limite:
        r = js(w, t, JS_PASO)
        if r == "SIN_CITAS":
            return "sin_citas", []
        if r.startswith("TRAMITE"):
            opciones = r.split("\n")[1:]
            return ("objetivo" if any(es_objetivo(o, ciudades) for o in opciones) else "otras"), opciones
        time.sleep(SONDEO)
    raise TimeoutError(f"sin resultado en {TIMEOUT_CICLO}s (último estado: {r})")


def elegir_opcion(opciones, ciudades):
    """La primera opción objetivo, respetando el orden de las ciudades pedidas."""
    for c in ciudades:
        for o in opciones:
            if es_objetivo(o, [c]):
                return o
    return None


def avanzar(w, t, opcion):
    """Elige la opción en "Trámite" y da clic en "Siguiente".

    Devuelve (resultado, detalle), con resultado:
      paso_dos  la plataforma pasó a elegir ciudad, sede, fecha y hora
      sin_cupo  la plataforma respondió que ya no hay citas
      fallo     no se pudo avanzar; la pestaña queda en "Trámite"
    """
    codigo = JS_AVANZAR.replace("__OBJETIVO__", json.dumps(opcion))
    r = ""
    paso_dos_desde = None
    inicio = time.time()
    limite = inicio + TIMEOUT_AVANCE
    while time.time() < limite:
        r = js(w, t, codigo)
        if r.startswith("SIN_CUPO"):
            return "sin_cupo", " ".join(r.split("\n")[1:])
        if r in ("SIN_SELECT", "SIN_OPCION"):
            return "fallo", r
        if r == "ESPERANDO_BOTON" and time.time() - inicio > ESPERA_BOTON:
            return "fallo", f"el botón Siguiente no se habilitó en {ESPERA_BOTON}s"
        if r == "PASO_DOS":
            # Espera un momento por si la plataforma muestra el aviso de "sin citas" al cargar.
            paso_dos_desde = paso_dos_desde or time.time()
            if time.time() - paso_dos_desde >= ESPERA_PASO_DOS:
                return "paso_dos", ""
        time.sleep(SONDEO)
    if paso_dos_desde:
        return "paso_dos", ""
    return "fallo", f"sin respuesta en {TIMEOUT_AVANCE}s (último estado: {r})"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ciudad", nargs="+", default=["Bogotá"], metavar="CIUDAD",
                    help=f"una o varias ciudades a vigilar (por defecto Bogotá). Opciones: {', '.join(CIUDADES)}")
    ap.add_argument("--intervalo", type=int, default=INTERVALO_MIN,
                    help=f"segundos entre revisiones; solo se puede aumentar (mínimo {INTERVALO_MIN})")
    ap.add_argument("--enfocar", action="store_true",
                    help="al encontrar la cita, traer Chrome al frente (quita el foco a la app que estés usando)")
    ap.add_argument("--una-vez", action="store_true", help="hacer una sola revisión y salir")
    ap.add_argument("--probar-notificacion", action="store_true",
                    help="enviar una notificación de prueba al teléfono y salir")
    args = ap.parse_args()

    if args.probar_notificacion:
        log(f"Tema de ntfy (suscríbete a este nombre en la app): {obtener_topic_ntfy()}")
        notificar_telefono("Prueba del monitor de citas", "Si ves esto, las alertas al teléfono funcionan.")
        return

    ciudades = [c.strip() for c in args.ciudad if c.strip()]
    if args.intervalo < INTERVALO_MIN:
        log(f"El intervalo mínimo es {INTERVALO_MIN}s; revisar más seguido puede hacer que la plataforma "
            f"bloquee las revisiones. Se usará {INTERVALO_MIN}s.")
    intervalo = max(INTERVALO_MIN, args.intervalo)

    w, t = pestana_dedicada()
    log(f"Vigilando: {', '.join(ciudades)}. Usando tu Chrome: ventana {w}, pestaña {t}. "
        "No cierres esa pestaña; puedes usar Chrome normalmente en otras.")
    intento = 0
    while True:
        intento += 1
        try:
            estado, opciones = revisar(w, t, ciudades)
        except ErrorChrome as e:
            if pestana_perdida(e):
                log("La pestaña del monitor ya no existe (se cerró o Chrome se reinició); buscando otra.")
                w, t = pestana_dedicada()
                continue
            log(f"#{intento} {e}")
            if "Apple Events" in str(e) or "Automatización" in str(e):
                sys.exit(1)
            estado = "error"
        except TimeoutError as e:
            log(f"#{intento} plataforma lenta: {e}. Reintento luego.")
            estado = "error"

        if estado == "sin_citas":
            log(f"#{intento} sin citas disponibles.")
        elif estado == "otras":
            log(f"#{intento} hay trámites, pero no el de vehículos eléctricos o híbridos en "
                f"{', '.join(ciudades)} (sin aviso): " + "; ".join(opciones))
        elif estado == "objetivo":
            log(f"#{intento} ¡DISPONIBLE! {'; '.join(opciones)}")
            elegida = elegir_opcion(opciones, ciudades)
            log(f"#{intento} Eligiendo \"{elegida}\" y dando clic en Siguiente...")
            try:
                resultado, detalle = avanzar(w, t, elegida)
            except ErrorChrome as e:
                resultado, detalle = "fallo", str(e)

            if resultado == "sin_cupo":
                log(f"#{intento} Al dar clic en Siguiente, la plataforma respondió que ya no hay citas "
                    f"({detalle or 'sin detalle'}). Sin aviso; sigo vigilando.")
            else:
                mostrar_pestana(w, t, enfocar=args.enfocar)
                try:
                    js(w, t, JS_RESALTAR)
                except ErrorChrome:
                    pass
                if resultado == "paso_dos":
                    log(f"#{intento} La plataforma pasó al paso 2 (ciudad, sede, fecha y hora).")
                    mensaje = (f"{elegida}. Tu Chrome ya avanzó al paso 2: elige sede, fecha y hora, "
                               "y completa tus datos.")
                else:
                    log(f"#{intento} No se pudo avanzar automáticamente ({detalle}). "
                        "La pestaña quedó en 'Trámite'.")
                    mensaje = f"{elegida}. Tu Chrome ya está en Trámite: elige la opción y continúa."
                notificar("Cita disponible: vehículos eléctricos o híbridos", mensaje)
                log("Monitor detenido para que completes el agendamiento en tu Chrome.")
                return

        if args.una_vez:
            return
        espera = intervalo + random.randint(0, intervalo // 3)
        log(f"Próxima revisión en {espera}s")
        time.sleep(espera)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Monitor detenido por el usuario.")
