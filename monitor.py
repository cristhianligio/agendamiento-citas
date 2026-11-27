#!/usr/bin/env python3
"""
Monitor de citas para la devolución del IVA de vehículos eléctricos o híbridos.

Trabaja en TU Google Chrome (tu perfil y tus sesiones): controla una pestaña con
AppleScript, recorre Agendar cita > Persona Natural > Videoatención > Devoluciones
y revisa el campo "Trámite". Solo avisa si aparece el trámite de vehículos
eléctricos o híbridos para la ciudad elegida. En ese caso elige esa opción, la
primera fecha disponible y la primera hora, y da clic en "Siguiente" hasta el
formulario de cédula y captcha. Solo avisa si ese formulario carga. Si la plataforma
responde que no hay citas o muestra un paso vacío, sigue vigilando.
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
TIMEOUT_AVANCE = 90  # s máximos para llegar del trámite al formulario de cédula
ESPERA_BOTON = 5     # s máximos para que se habilite "Siguiente" tras elegir el trámite
ESPERA_FORMULARIO = 20  # s máximos para que un paso que ya se mostró cargue su formulario
ESPERA_PASO_DOS_AUTO = 45  # s máximos para elegir fecha y hora en el paso 2

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

# JavaScript que avanza solo hasta el paso 3 (cédula y captcha). Se ejecuta en cada
# sondeo y hace como mucho UNA acción por llamada:
#   paso 1: elige el trámite __OBJETIVO__ y da clic en "Siguiente";
#   paso 2: elige la primera fecha habilitada del calendario, la primera hora y da
#           clic en "Siguiente".
# No llena datos personales ni toca el captcha.
JS_AVANZAR = r"""
(function (objetivo) {
  var vis = function (el) {
    return !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  var q = function (sel) { return document.querySelector(sel); };
  var modales = ['ModalSinCitas', 'ModalError'];
  for (var i = 0; i < modales.length; i++) {
    var m = q('div[nombre="' + modales[i] + '"]');
    if (vis(m)) {
      var txt = Array.prototype.map.call(m.querySelectorAll('div[nombre="txtTituloModal"], div[nombre="txtInfoAdicional"]'),
        function (x) { return x.textContent.trim(); }).filter(Boolean).join(' ');
      return 'SIN_CUPO\n' + txt.replace(/\s+/g, ' ');
    }
  }
  var est = window.__monitorAvance || (window.__monitorAvance = {});

  // Paso 3: formulario de cédula y captcha.
  // Cuenta como cargado si aparece cualquiera de sus elementos: el captcha, el campo de
  // cédula, "Tipo de documento" o el bloque con los datos que la plataforma ya tiene.
  if (vis(q('div[nombre="PasoTres"]'))) {
    var P3 = 'div[nombre="PasoTres"] ';
    var cap = q(P3 + 'div[nombre="Captcha"]');
    var hay = [];
    if (cap && vis(cap.querySelector('iframe'))) hay.push('captcha');
    if (vis(q('div[pantalla="PasoTres"][nombre="tbxNumeroDoc"] input'))) hay.push('campo de cédula');
    if (vis(q(P3 + 'div[nombre="TipoDocumento"]'))) hay.push('tipo de documento');
    if (vis(q(P3 + 'div[nombre="txtInfoAsociada"]')) || vis(q(P3 + 'div[nombre="DatosCorretos"]'))) hay.push('datos registrados');
    return hay.length ? 'PASO_TRES_LISTO\n' + hay.join(', ') : 'PASO_TRES_VACIO';
  }

  // Paso 2: fecha, hora y "Siguiente".
  var P2 = 'div[nombre="PasoDos"] ';
  if (vis(q('div[nombre="PasoDos"]'))) {
    var btnFecha = q(P2 + 'div[nombre="btnFecha"]');
    if (!vis(btnFecha)) return 'PASO_DOS_VACIO';
    if (!est.fecha) {
      var cal = q(P2 + 'div[nombre="Calendario"]');
      var celdas = cal ? Array.prototype.filter.call(cal.querySelectorAll('td[role="gridcell"]'), function (td) {
        return td.querySelector('.k-link') && !td.classList.contains('k-state-disabled') && !td.classList.contains('k-disabled');
      }) : [];
      if (celdas.length) {
        var link = celdas[0].querySelector('.k-link');
        link.click();
        est.fecha = Date.now();
        return 'P2 FECHA ' + (link.getAttribute('title') || celdas[0].getAttribute('title') || link.textContent.trim());
      }
      if (cal && !cal.classList.contains('calendario-open') && !est.abrioCal) {
        btnFecha.click(); est.abrioCal = 1; return 'P2 ABRIR_CALENDARIO';
      }
      var sig = cal && cal.querySelector('.k-nav-next, .k-calendar-nav-next');
      if (sig && cal.querySelector('td[role="gridcell"]') && (est.meses || 0) < 3) {
        sig.click(); est.meses = (est.meses || 0) + 1; return 'P2 MES_SIGUIENTE';
      }
      return 'P2 ESPERANDO_FECHA';
    }
    if (!est.hora) {
      if (Date.now() - est.fecha < 1500) return 'P2 ESPERANDO_HORA';
      var hs = q(P2 + 'div[nombre="Horas"] select');
      var op = vis(hs) && Array.prototype.find.call(hs.options, function (o) { return o.value !== '' && o.text.trim(); });
      if (!op) return 'P2 ESPERANDO_HORA';
      hs.selectedIndex = op.index;
      hs.dispatchEvent(new Event('input', {bubbles: true}));
      hs.dispatchEvent(new Event('change', {bubbles: true}));
      est.hora = 1;
      return 'P2 HORA ' + op.text.trim();
    }
    if (!est.siguiente2) {
      var b2 = q(P2 + 'div[nombre="btnSiguiente"]');
      if (vis(b2)) { b2.click(); est.siguiente2 = 1; return 'P2 CLIC siguiente'; }
      return 'P2 ESPERANDO_BOTON';
    }
    return 'P2 ESPERANDO_PASO_TRES';
  }

  // Paso 1: trámite y "Siguiente".
  var P = 'div[nombre="PasoUno"] ';
  if (!est.elegido) {
    var sel = q(P + 'div[nombre="Servicios"] select');
    if (!vis(sel)) return 'SIN_SELECT';
    var opt = Array.prototype.find.call(sel.options, function (o) { return o.text.trim() === objetivo; });
    if (!opt) return 'SIN_OPCION';
    sel.selectedIndex = opt.index;
    sel.dispatchEvent(new Event('input', {bubbles: true}));
    sel.dispatchEvent(new Event('change', {bubbles: true}));
    est.elegido = 1;
    return 'ELEGIDO';
  }
  if (!est.siguiente) {
    var b = q(P + 'div[nombre="btnSiguiente"]');
    if (vis(b)) { b.click(); est.siguiente = 1; return 'CLIC siguiente'; }
    return 'ESPERANDO_BOTON';
  }
  return 'ESPERANDO';
})(__OBJETIVO__)
"""

JS_RESALTAR = r"""
(function () {
  var vis = function (el) { return !!el && el.getClientRects().length > 0; };
  var ced = document.querySelector('div[pantalla="PasoTres"][nombre="tbxNumeroDoc"] input');
  var p3 = document.querySelector('div[nombre="PasoTres"]');
  if (vis(ced)) {
    ced.scrollIntoView({block: 'center'}); ced.style.outline = '4px solid #16a34a'; ced.focus();
  } else if (vis(p3)) {
    var cap = p3.querySelector('div[nombre="Captcha"]');
    (vis(cap) ? cap : p3).scrollIntoView({block: 'start'});
  } else if (vis(document.querySelector('div[nombre="PasoDos"]'))) {
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
    """Avanza solo hasta el formulario de cédula y captcha (paso 3).

    Paso 1: elige la opción en "Trámite" y da clic en "Siguiente".
    Paso 2: elige la primera fecha disponible, la primera hora y da clic en "Siguiente".

    Devuelve (resultado, detalle), con resultado:
      paso_tres            cargó el formulario de cédula y captcha
      paso_dos_incompleto  el paso 2 cargó Fecha, pero no se logró terminarlo solo
      sin_formulario       el paso 2 o el 3 se mostró sin su formulario
      sin_cupo             la plataforma mostró un aviso de que ya no hay citas
      fallo                no se pudo avanzar desde el paso 1
    """
    codigo = JS_AVANZAR.replace("__OBJETIVO__", json.dumps(opcion))
    r = ""
    pasos = []            # lo que se eligió en el paso 2, para el registro
    p2_desde = None       # primera vez que se vio el paso 2 con Fecha
    vacio2_desde = None
    vacio3_desde = None
    inicio = time.time()
    limite = inicio + TIMEOUT_AVANCE
    while time.time() < limite:
        r = js(w, t, codigo)
        if r.startswith("SIN_CUPO"):
            return "sin_cupo", " ".join(r.split("\n")[1:])
        if r.startswith("PASO_TRES_LISTO"):
            return "paso_tres", "; ".join(pasos + r.split("\n")[1:])
        if r == "PASO_TRES_VACIO":
            vacio3_desde = vacio3_desde or time.time()
            if time.time() - vacio3_desde >= ESPERA_FORMULARIO:
                return "sin_formulario", f"el paso 3 no cargó el captcha ni el formulario en {ESPERA_FORMULARIO}s"
        elif r == "PASO_DOS_VACIO":
            vacio2_desde = vacio2_desde or time.time()
            if time.time() - vacio2_desde >= ESPERA_FORMULARIO:
                return "sin_formulario", f"el paso 2 no cargó el campo Fecha en {ESPERA_FORMULARIO}s"
        elif r.startswith("P2 "):
            p2_desde = p2_desde or time.time()
            if r.startswith(("P2 FECHA ", "P2 HORA ")):
                pasos.append(r[3:].replace("FECHA ", "fecha: ").replace("HORA ", "hora: "))
            if time.time() - p2_desde >= ESPERA_PASO_DOS_AUTO:
                return "paso_dos_incompleto", f"último estado: {r[3:]}"
        elif r in ("SIN_SELECT", "SIN_OPCION"):
            return "fallo", r
        elif r == "ESPERANDO_BOTON" and time.time() - inicio > ESPERA_BOTON:
            return "fallo", f"el botón Siguiente no se habilitó en {ESPERA_BOTON}s"
        time.sleep(SONDEO)
    if p2_desde:
        return "paso_dos_incompleto", f"último estado: {r[3:] if r.startswith('P2 ') else r}"
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
                log(f"#{intento} La plataforma mostró un aviso de que ya no hay citas "
                    f"({detalle or 'sin detalle'}). Sin aviso; sigo vigilando.")
            elif resultado == "sin_formulario":
                log(f"#{intento} La plataforma no cargó el formulario ({detalle}). Sin aviso; sigo vigilando.")
            elif resultado == "fallo":
                log(f"#{intento} No se pudo avanzar automáticamente ({detalle}). Sin aviso; sigo vigilando.")
            else:
                if resultado == "paso_tres":
                    log(f"#{intento} Cargó el paso 3 del formulario ({detalle}).")
                    mensaje = (f"{elegida}. Tu Chrome ya está en el formulario del captcha, con fecha y hora "
                               "elegidas: resuelve el captcha y completa tus datos.")
                else:
                    log(f"#{intento} El paso 2 cargó Fecha, pero no se pudo terminar solo ({detalle}).")
                    mensaje = (f"{elegida}. Tu Chrome está en el paso 2 con Fecha cargada: "
                               "elige fecha y hora, da clic en Siguiente y completa tus datos.")
                mostrar_pestana(w, t, enfocar=args.enfocar)
                try:
                    js(w, t, JS_RESALTAR)
                except ErrorChrome:
                    pass
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
