# Monitor de citas: devolución del IVA de vehículos eléctricos o híbridos

Script para facilitar la consecución de citas para la **devolución del IVA de vehículos híbridos y/o eléctricos**. Revisa la disponibilidad de citas por videoatención y te avisa en el teléfono y en el Mac en cuanto aparece el trámite de tu ciudad.

Es ideal para **Bogotá, Medellín, Cali y Bucaramanga**, las ciudades donde se ofrece este trámite.

Las citas se ocupan en segundos. Por eso, cuando el monitor encuentra disponibilidad, deja tu Chrome ya en el campo **Trámite**, al frente y resaltado, para que solo tengas que elegir la opción y continuar.

## Qué hace y qué no hace

**Hace:**
- Abre la plataforma de agendamiento en una pestaña de **tu propio Google Chrome**, con tu perfil.
- Repite el recorrido *Agendar cita → Persona Natural → Videoatención → Devoluciones* cada 60 a 80 segundos.
- Si en el campo **Trámite** aparece la devolución para vehículos eléctricos o híbridos de tu ciudad, te avisa y se detiene con la pestaña lista.

**No hace:**
- **No llena datos personales ni resuelve el captcha.** La notificación solo te indica que hay disponibilidad. Tú debes completar tus datos personales y resolver el captcha.
- No reserva la cita por ti ni garantiza que la consigas: otras personas pueden tomarla antes.

> **Importante:** el usuario es absolutamente responsable por el proceso con la entidad de impuestos nacional, incluida la información que entrega, la cita que agenda y el trámite de devolución.

## Requisitos

- **macOS.** El monitor usa AppleScript y herramientas propias de macOS, así que no funciona en Windows ni en Linux.
- **Google Chrome.**
- **Python 3**, el que trae macOS. Si al ejecutar `python3` el sistema te pide instalar las herramientas de desarrollo, acepta. No hace falta instalar paquetes adicionales.
- Opcional: la app gratuita **ntfy** en tu teléfono ([iOS](https://apps.apple.com/app/ntfy/id1625396347) o [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)), para recibir los avisos lejos del computador.

## Instalación

```bash
git clone https://github.com/cristhianligio/agendamiento-citas.git
cd agendamiento-citas
```

### 1. Permitir que el monitor controle Chrome

1. En Chrome, ve a **Visualización → Opciones para desarrolladores → Permitir JavaScript desde Apple Events**. Si tu Chrome está en inglés: **View → Developer → Allow JavaScript from Apple Events**.
2. La primera vez que ejecutes el monitor, macOS te preguntará si la Terminal puede controlar Google Chrome. Acepta. Si lo rechazaste, actívalo en **Ajustes del Sistema → Privacidad y seguridad → Automatización**.

> **Seguridad:** mientras esa opción de Chrome está activa, cualquier aplicación con permiso de Automatización puede ejecutar código en todas tus pestañas, incluidas las de tu banco. **Desactívala cuando termines de usar el monitor.**

### 2. Configurar los avisos en el teléfono (opcional)

```bash
python3 monitor.py --probar-notificacion
```

La primera vez se crea el archivo `ntfy_topic.txt`, con un nombre de tema aleatorio y privado, y se muestra en la pantalla. En la app ntfy, toca **+**, escribe ese nombre exacto y suscríbete. Luego vuelve a ejecutar el comando: debe llegarte la notificación de prueba.

- **iPhone:** en *Ajustes → Notificaciones → ntfy*, activa las notificaciones, los sonidos y, si está disponible, **Notificaciones críticas** o **Urgentes**, para que suenen aunque esté activado un modo de Concentración.
- **El nombre del tema funciona como una contraseña.** Cualquiera que lo conozca puede leer tus avisos, así que no lo compartas. Los avisos no incluyen datos personales.

## Uso

```bash
python3 monitor.py                           # vigila Bogotá
python3 monitor.py --ciudad Medellín         # otra ciudad
python3 monitor.py --ciudad Cali Bucaramanga # varias ciudades
python3 monitor.py --una-vez                 # una sola revisión, para probar
```

Mientras corre:
- **No cierres la pestaña que usa el monitor** ni hagas clic en ella. Puedes usar Chrome con normalidad en otras ventanas y pestañas. Si la cierras, el monitor abre otra.
- No minimices esa ventana: Chrome puede ralentizar las pestañas minimizadas. Déjala detrás de otras ventanas.
- Para detenerlo, presiona `Ctrl+C` en la Terminal.

Cuando aparece la cita, recibes el aviso en el teléfono, una notificación con sonido en el Mac, y Chrome pasa al frente con el campo **Trámite** resaltado. Elige la opción, completa tus datos y resuelve el captcha.

### Dejarlo corriendo en segundo plano

Así sigue funcionando aunque cierres la Terminal, y el Mac no entra en reposo:

```bash
nohup caffeinate -i python3 -u monitor.py >> monitor.log 2>&1 &
```

Para ver lo que va haciendo:

```bash
tail -f monitor.log
```

Para detenerlo:

```bash
pkill -f monitor.py
```

## Tiempo entre revisiones

El monitor revisa **cada 60 segundos como mínimo**, más un margen aleatorio de hasta 20 segundos. **No es posible reducir este tiempo:** revisar con más frecuencia podría hacer que el sistema de seguridad de la plataforma bloquee las revisiones. La opción `--intervalo` solo permite aumentarlo.

## Soporte y issues

Se atenderán issues mientras la plataforma de agendamiento no tenga cambios extensos. Si la plataforma cambia de forma significativa, por ejemplo con un nuevo diseño o un nuevo flujo de agendamiento, es posible que el monitor deje de funcionar y no se actualice.

Al reportar un problema, incluye la versión de macOS, la versión de Chrome y las últimas líneas que muestra el monitor, **sin datos personales ni el nombre de tu tema de ntfy**.

## Aviso legal

Este proyecto es independiente y no está afiliado, respaldado ni patrocinado por ninguna entidad pública. Se ofrece "tal cual", sin garantías, bajo la [licencia MIT](LICENSE). Úsalo bajo tu propia responsabilidad y respetando los términos de uso de la plataforma de agendamiento.
