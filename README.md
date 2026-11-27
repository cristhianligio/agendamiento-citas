# Monitor de citas: devolución del IVA de vehículos eléctricos o híbridos

Script para facilitar la consecución de citas para la **devolución del IVA de vehículos híbridos y/o eléctricos**. Revisa la disponibilidad de citas por videoatención y te avisa en el teléfono y en el Mac en cuanto aparece el trámite de tu ciudad.

Es ideal para **Bogotá, Medellín, Cali y Bucaramanga**, las ciudades donde se ofrece este trámite y es necesario conseguir una cita para poder enviar los documentos.

Las citas se ocupan en segundos. Por eso, cuando el monitor encuentra disponibilidad, avanza solo hasta el formulario donde se escribe la cédula: elige el trámite de tu ciudad, la fecha disponible más cercana y la primera hora. Así, cuando te avisa, solo te falta completar tus datos y resolver el captcha.

## Qué hace y qué no hace

**Hace:**
- Abre la plataforma de agendamiento en una pestaña de **tu propio Google Chrome**, con tu perfil.
- Repite el recorrido *Agendar cita → Persona Natural → Videoatención → Devoluciones* cada 60 a 80 segundos.
- Si en el campo **Trámite** aparece la devolución para vehículos eléctricos o híbridos de tu ciudad, elige esa opción y da clic en **Siguiente**.
- En el paso de fecha y hora, elige la fecha disponible más cercana y la primera hora, y da clic en **Siguiente**.
- Solo te avisa si carga el formulario de cédula y captcha. En ese caso se detiene con la pestaña lista.
- No te avisa, y sigue vigilando, si la plataforma responde que ya no hay citas, si muestra un paso vacío (sin el campo de fecha o sin el campo de cédula) o si no logra avanzar desde el campo **Trámite**.

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
- **Si los avisos aparecen al abrir la app pero no llegan como notificación**, el iPhone dejó de estar registrado para recibir avisos de ese tema. Elimina el tema en la app ntfy, ciérrala por completo, vuelve a suscribirte con el mismo nombre y repite `python3 monitor.py --probar-notificacion` con el teléfono bloqueado.

## Uso

```bash
python3 monitor.py                           # vigila Bogotá
python3 monitor.py --ciudad Medellín         # otra ciudad
python3 monitor.py --ciudad Cali Bucaramanga # varias ciudades
python3 monitor.py --una-vez                 # una sola revisión, para probar
python3 monitor.py --enfocar                 # al encontrar la cita, trae Chrome al frente
```

Mientras corre:
- **No cierres la pestaña que usa el monitor** ni hagas clic en ella. Puedes usar Chrome con normalidad en otras ventanas y pestañas. Si la cierras, el monitor abre otra.
- No minimices esa ventana: Chrome puede ralentizar las pestañas minimizadas. Déjala detrás de otras ventanas.
- Para detenerlo, presiona `Ctrl+C` en la Terminal.

Cuando aparece la cita, recibes el aviso en el teléfono y una notificación con sonido en el Mac, y la pestaña del monitor queda con el título **¡CITA DISPONIBLE!** en el formulario de cédula y captcha, con la fecha y la hora ya elegidas. Ve a esa pestaña, completa tus datos y resuelve el captcha.

A veces la plataforma muestra un paso vacío, sin campos para continuar. En ese caso no es posible agendar, así que el monitor no avisa: lo anota en su registro y sigue vigilando. Si el paso de fecha y hora sí carga, pero el monitor no logra terminarlo solo, te avisa igual para que elijas la fecha y la hora tú.

El monitor **no le quita el foco** a la aplicación que estés usando: puedes seguir escribiendo en otra app mientras revisa. Lo más cómodo es dejar la ventana de Chrome del monitor visible en otra pantalla o detrás de tus ventanas. Si prefieres que Chrome pase al frente automáticamente al encontrar la cita, usa `--enfocar`.

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
