# Dashboard de Ventas

Es una pantalla que muestra, en un solo lugar, cómo van las ventas de las tres
empresas del grupo: **Quimand**, **Dogaresa** y **Yeso La Limeña**.

Toma los mismos reporteadores en Excel que ya se sacan del sistema y los
convierte en gráficos: cuánto se vendió, quiénes son los mejores clientes, qué
productos se mueven más y si vamos adelantados o atrasados respecto a la meta
del año.

No reemplaza al sistema ni le escribe nada: solo lee los Excel.

---

## Cómo se abre

Doble clic en el archivo **`Abrir Dashboard.bat`** (el que está en esta misma
carpeta).

Se abre una ventana negra con letras y, a los pocos segundos, el dashboard
aparece solo en el navegador (Chrome, Edge, el que se use normalmente).

Tres cosas que conviene saber:

- **La primera vez demora más.** La computadora tiene que instalar unas piezas;
  puede tardar unos minutos. Solo pasa una vez.
- **No cierres la ventana negra** mientras estés usando el dashboard. Es la que
  lo mantiene funcionando. Se puede minimizar sin problema.
- **Para cerrar todo:** cierra primero la pestaña del navegador y después la
  ventana negra.

---

## Cómo se cargan los Excel cada semana

Cada semana se descargan del sistema los tres reporteadores, uno por empresa:

| Empresa | Archivo |
|---|---|
| Quimand | `REPORTEADOR INDUSTRIAL.xls` |
| Dogaresa | `REPORTEADOR SOCIEDAD MINERA.xls` |
| Yeso La Limeña | `REPORTEADOR YESO LA LIMENA.xls` |

En el dashboard, en el panel de la izquierda, hay un recuadro que dice
**"Arrastra los archivos aquí"**. Se seleccionan los tres archivos y se sueltan
ahí (o se hace clic en el recuadro y se buscan en la carpeta donde se
descargaron).

El dashboard reconoce solo a qué empresa pertenece cada archivo por su nombre,
así que **no importa el orden** en que se suban. Tampoco hay que cambiarles el
nombre ni abrirlos antes: se suben tal cual salen del sistema.

Cuando termina de leerlos, avisa cuántas filas cargó y de qué fechas. Si
detecta algo raro (filas sin fecha, un cliente escrito de varias formas) lo dice
en un mensaje amarillo; es solo informativo, el dashboard sigue funcionando.

> Los archivos se leen en el momento y no se guardan. La próxima vez que se abra
> el dashboard hay que volver a subirlos: es lo normal y toma diez segundos.

---

## Dónde se editan las metas

En el panel de la izquierda hay una sección **"Metas del año"**.

Ahí se escribe la meta anual en soles de cada empresa (por ejemplo `36220000`
para Quimand) y se da **Guardar**.

**Las metas quedan grabadas.** No hay que volver a escribirlas la próxima vez ni
descargar ni subir ningún archivo: la computadora las recuerda sola. Se pueden
cambiar cuando se quiera; basta con escribir el nuevo número y volver a guardar.

Las metas se guardan **por año**, así que al empezar un año nuevo se cargan las
metas nuevas y las del año pasado se conservan para poder compararlas.

Con la meta cargada, el dashboard reparte el año en meses siguiendo la
estacionalidad real del negocio —los meses que históricamente venden más
reciben una parte mayor de la meta— y muestra si a la fecha de hoy vamos
adelantados o atrasados.

Si una empresa todavía no tiene meta cargada, el dashboard funciona igual: solo
que para esa empresa no muestra el semáforo de avance.

---

## Si algo falla

**Se abre la ventana negra y dice que no encuentra Python.**
Hay que instalarlo una sola vez. La misma ventana explica los pasos: entrar a
`python.org/downloads`, descargar, y —muy importante— marcar la casilla
**"Add python.exe to PATH"** antes de dar Install. Después, doble clic otra vez
en `Abrir Dashboard.bat`.

**Dice que no pudo instalar las librerías.**
Casi siempre es la conexión a internet o que la red de la oficina bloquea la
descarga. Revisar el internet y volver a intentar.

**La ventana negra se abre y se cierra sola al instante.**
Puede que el archivo `.bat` se haya copiado a otra carpeta. Tiene que quedar
dentro de la carpeta `dashboard`, junto a `app.py`.

**El navegador no se abre solo.**
Abrirlo a mano y escribir en la barra de direcciones: `http://localhost:8501`

**Sale un error rojo al subir un Excel.**
Suele ser que el archivo no es el reporteador (por ejemplo, se subió otro
reporte) o que se abrió y guardó en Excel cambiándole el formato. Volver a
descargarlo del sistema y subirlo sin abrirlo.

**Los números no cuadran con el sistema.**
Revisar los interruptores del panel izquierdo: hay opciones para incluir o
excluir las ventas entre empresas del grupo y los servicios (fletes,
alquileres). Según cómo estén, el total cambia.

**Cualquier otra cosa.**
Tomar una foto de la pantalla —incluida la ventana negra si dice algo— y
enviarla a sistemas.
