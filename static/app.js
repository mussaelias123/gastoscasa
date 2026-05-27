/*
================================================================================
ARCHIVO: static/app.js
================================================================================

QUÉ ES ESTE ARCHIVO:
  Contiene el código JavaScript que corre en el NAVEGADOR (cliente).
  No corre en el servidor Python. El servidor Flask simplemente lo "sirve"
  (lo descarga al navegador como si fuera un archivo estático, como una imagen).

ROL EN EL PROYECTO:
  Frontend → Lógica del cliente (interactividad en el navegador)

LA DIFERENCIA FUNDAMENTAL ENTRE BACKEND Y FRONTEND:

  BACKEND (app.py, database.py) — corre en TU PC donde está Flask:
    - Tiene acceso a la base de datos
    - Tiene acceso al sistema de archivos
    - El usuario NUNCA ve este código directamente
    - Genera el HTML y lo envía al navegador

  FRONTEND (este archivo, style.css, los .html) — corre en el NAVEGADOR:
    - El usuario SÍ puede ver este código (click derecho → Ver código fuente)
    - No tiene acceso directo a la base de datos
    - Maneja la interactividad: clicks, animaciones, validaciones visuales
    - Se comunica con el backend via peticiones HTTP (GET/POST)

ANALOGÍA CON PLCs:
  El backend es la lógica del PLC (no visible para el operador).
  El frontend es la pantalla HMI (lo que ve y toca el operador).
  JavaScript es el "script" de la pantalla HMI que maneja eventos
  de botones y actualiza la visualización.

CUÁNDO CORRE ESTE CÓDIGO:
  El navegador descarga este archivo junto con el HTML.
  El código dentro de document.addEventListener('DOMContentLoaded', ...)
  se ejecuta una vez que el HTML terminó de cargarse.
  Las funciones individuales se ejecutan cuando el usuario hace alguna acción.

================================================================================
*/


/*
  DOMContentLoaded: evento que se dispara cuando el navegador terminó de
  "parsear" (interpretar) el HTML y construir el DOM (Document Object Model).
  DOM = representación en memoria del HTML como un árbol de objetos.
  No se puede manipular el HTML antes de que este evento ocurra.

  Es como esperar a que el PLC termine el arranque antes de ejecutar el programa.
*/
// Función de ordenamiento expuesta para que initFormAjax pueda llamarla
var ordenarTablaFn = null;

// Categorías disponibles por tipo de movimiento
var CATEGORIAS = {
    gasto:   ['No Definido', 'Fijo', 'Comida y bebida', 'Entretenimiento', 'Salud', 'Transporte',
               'Servicios', 'Ropa', 'Hogar', 'Educación', 'Turismo', 'Cambio', 'Mascotas', 'Familia/Amigos', 'Otros'],
    ingreso: ['Sueldo', 'Láser', 'Venta', 'Cambio', 'Otros']
};

// Llena un <select> con las categorías correspondientes al tipo dado.
// Si se pasa valorSeleccionado, pre-selecciona esa opción.
function llenarSelectCategorias(selectEl, tipo, valorSeleccionado) {
    selectEl.innerHTML = '';
    var cats = CATEGORIAS[tipo] || CATEGORIAS.gasto;
    cats.forEach(function(cat) {
        var opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        if (cat === valorSeleccionado) opt.selected = true;
        selectEl.appendChild(opt);
    });
}

document.addEventListener('DOMContentLoaded', function() {

    console.log('✓ app.js cargado y ejecutándose en el navegador');
    /*
      console.log(): muestra un mensaje en la "Consola" del navegador.
      Para verla: F12 → pestaña "Console".
      Es la herramienta de debugging del frontend (como el monitoreo de
      variables en el PLC desde el software de programación).
    */

    // Inicializamos las funcionalidades de la página
    inicializarFechaHoy();
    inicializarFormatoMonto();
    inicializarPersona();
    inicializarColoresDinamicos();
    resaltarNavActual();
    inicializarCategorias();
    initFiltros();
    initOrden();
    initSelectVista();
    initEdicionInline();
    initFormAjax();

    console.log('✓ Funcionalidades inicializadas');
});


/*
================================================================================
FUNCIÓN: mostrarModalBorrado(form)
================================================================================
Propósito:
  Muestra un modal de confirmación antes de borrar un gasto.
  Reemplaza el confirm() nativo (que bloqueaba el browser bajo automatización).

Cómo se usa (en index.html):
  <button type="button" onclick="mostrarModalBorrado(this.closest('form'))">✕</button>
================================================================================
*/
(function () {
    var formPendiente = null;
    var modal = null;

    function inicializarModal() {
        modal = document.getElementById('modal-confirmacion');
        document.getElementById('modal-confirmar').addEventListener('click', function () {
            if (formPendiente) {
                formPendiente.submit();
            }
        });
        document.getElementById('modal-cancelar').addEventListener('click', function () {
            modal.classList.remove('visible');
            formPendiente = null;
            console.log('Borrado cancelado por el usuario');
        });
    }

    window.mostrarModalBorrado = function (form) {
        formPendiente = form;
        modal.classList.add('visible');
    };

    document.addEventListener('DOMContentLoaded', inicializarModal);
})();


/*
================================================================================
FUNCIÓN: inicializarCategorias()
================================================================================
Propósito:
  En el formulario de nuevo movimiento:
  1. Llena el <select id="categoria"> con las opciones del tipo activo.
  2. Actualiza las opciones cuando el usuario cambia el tipo (ingreso/gasto).
  3. Muestra u oculta la sección de envío según el tipo seleccionado.
  4. Muestra u oculta el campo de costo según el checkbox "Incluye envío".
================================================================================
*/
function inicializarCategorias() {
    var selectTipo      = document.getElementById('tipo');
    var selectCategoria = document.getElementById('categoria');
    var seccionEnvio    = document.getElementById('seccion-envio');
    var checkboxEnvio   = document.getElementById('incluye-envio');
    var campoEnvio      = document.getElementById('campo-costo-envio');
    var inputCostoEnvio = document.getElementById('costo_envio');
    var seccionCuotas   = document.getElementById('seccion-cuotas');
    var checkboxCuotas  = document.getElementById('incluye-cuotas');
    var campoCuotas     = document.getElementById('campo-total-cuotas');
    var inputTotalCuotas = document.getElementById('total_cuotas');

    // Elementos de Cambio
    var filaFlechaCambio  = document.getElementById('fila-flecha-cambio');
    var filaCambioDestino = document.getElementById('fila-cambio-destino');
    var filaMontoFinal    = document.getElementById('fila-monto-final');
    var selectMoneda      = document.getElementById('moneda');
    var selectMonedaFinal = document.getElementById('moneda_final');
    var inputMontoFinal   = document.getElementById('monto_final');
    var campoCategoria    = document.querySelector('.campo-rapido-categoria');

    if (!selectTipo || !selectCategoria) return;

    // Carga inicial: tipo es "gasto" por defecto.
    var valorActual = selectCategoria.dataset.valor || null;
    llenarSelectCategorias(selectCategoria, selectTipo.value || 'gasto', valorActual);

    // Mostrar sección cuotas en la carga inicial si el tipo es gasto
    if (seccionCuotas && selectTipo.value === 'gasto') seccionCuotas.style.display = '';

    // Función para mostrar/ocultar campos de Cambio
    function actualizarModoCambio(esCambio) {
        var filasCambio = [filaFlechaCambio, filaCambioDestino];
        filasCambio.forEach(function(el) {
            if (el) el.style.display = esCambio ? '' : 'none';
        });
        // Categoría: ocultar en modo cambio
        if (campoCategoria) campoCategoria.style.display = esCambio ? 'none' : '';
        // Envío y cuotas: ocultar en modo cambio
        if (seccionEnvio) seccionEnvio.style.display = esCambio ? 'none' : (selectTipo.value === 'gasto' ? '' : 'none');
        // Monto final: solo si monedas son diferentes
        actualizarMontoFinal();
    }

    // Función para mostrar/ocultar monto final según monedas
    function actualizarMontoFinal() {
        var esCambio = selectTipo.value === 'cambio';
        if (!esCambio || !selectMoneda || !selectMonedaFinal) {
            if (filaMontoFinal) filaMontoFinal.style.display = 'none';
            return;
        }
        var monedasDiferentes = selectMoneda.value !== selectMonedaFinal.value;
        if (filaMontoFinal) filaMontoFinal.style.display = monedasDiferentes ? '' : 'none';
        if (!monedasDiferentes && inputMontoFinal) inputMontoFinal.value = '';
    }

    // Escuchar cambios de moneda para toggle de monto final
    if (selectMoneda) selectMoneda.addEventListener('change', actualizarMontoFinal);
    if (selectMonedaFinal) selectMonedaFinal.addEventListener('change', actualizarMontoFinal);

    // Cuando cambia el tipo: actualizar categorías y visibilidad
    selectTipo.addEventListener('change', function() {
        var esCambio = selectTipo.value === 'cambio';
        var esGasto  = selectTipo.value === 'gasto';

        // Actualizar modo cambio
        actualizarModoCambio(esCambio);

        if (esCambio) {
            // Limpiar envío y cuotas
            if (checkboxEnvio) checkboxEnvio.checked = false;
            if (campoEnvio)    campoEnvio.style.visibility = 'hidden';
            if (inputCostoEnvio) inputCostoEnvio.value = '';
            if (seccionCuotas) seccionCuotas.style.display = 'none';
            if (checkboxCuotas) checkboxCuotas.checked = false;
            if (campoCuotas) campoCuotas.style.visibility = 'hidden';
            if (inputTotalCuotas) inputTotalCuotas.value = '';
            // Restaurar descripción si estaba en modo Fijo
            actualizarDescripcionSegunCategoria('');
            return;
        }

        // Flujo normal para gasto/ingreso
        llenarSelectCategorias(selectCategoria, selectTipo.value, null);
        if (seccionEnvio) seccionEnvio.style.display = esGasto ? '' : 'none';
        if (!esGasto) {
            if (checkboxEnvio) checkboxEnvio.checked = false;
            if (campoEnvio)    campoEnvio.style.visibility = 'hidden';
            if (inputCostoEnvio) inputCostoEnvio.value = '';
            if (seccionCuotas) seccionCuotas.style.display = 'none';
            if (checkboxCuotas) checkboxCuotas.checked = false;
            if (campoCuotas) campoCuotas.style.visibility = 'hidden';
            if (inputTotalCuotas) inputTotalCuotas.value = '';
        } else {
            if (seccionCuotas) seccionCuotas.style.display = '';
        }
        actualizarDescripcionSegunCategoria(selectCategoria.value);
    });

    // Cuando cambia la categoría: activar/desactivar modo Fijo
    selectCategoria.addEventListener('change', function() {
        actualizarDescripcionSegunCategoria(selectCategoria.value);
    });

    // Checkbox de envío: mostrar/ocultar campo de costo
    if (checkboxEnvio && campoEnvio) {
        checkboxEnvio.addEventListener('change', function() {
            campoEnvio.style.visibility = checkboxEnvio.checked ? 'visible' : 'hidden';
            if (!checkboxEnvio.checked && inputCostoEnvio) inputCostoEnvio.value = '';
        });
    }

    // Checkbox de cuotas: mostrar/ocultar campo de cantidad
    if (checkboxCuotas && campoCuotas) {
        checkboxCuotas.addEventListener('change', function() {
            campoCuotas.style.visibility = checkboxCuotas.checked ? 'visible' : 'hidden';
            if (!checkboxCuotas.checked && inputTotalCuotas) inputTotalCuotas.value = '';
        });
    }
}

/*
================================================================================
FUNCIÓN: actualizarDescripcionSegunCategoria(categoria)
================================================================================
Cuando la categoría es "Fijo", cambia el campo de descripción de texto libre
a un <select> con los gastos fijos definidos (variable global GASTOS_FIJOS).
Cuando se cambia a otra categoría, restaura el texto libre.
================================================================================
*/
function actualizarDescripcionSegunCategoria(categoria) {
    var inputDesc  = document.getElementById('descripcion');
    var selectFijo = document.getElementById('descripcion-fijo');
    if (!inputDesc || !selectFijo) return;

    var seccionCuotasDesc = document.getElementById('seccion-cuotas');
    var checkboxCuotasDesc = document.getElementById('incluye-cuotas');
    var campoCuotasDesc = document.getElementById('campo-total-cuotas');
    var inputTotalCuotasDesc = document.getElementById('total_cuotas');

    if (categoria === 'Fijo') {
        // Poblar el select con los gastos fijos disponibles
        var fijos = (typeof GASTOS_FIJOS !== 'undefined') ? GASTOS_FIJOS : [];
        selectFijo.innerHTML = '';
        if (fijos.length === 0) {
            var opt = document.createElement('option');
            opt.value = '';
            opt.textContent = '— Sin gastos fijos definidos —';
            selectFijo.appendChild(opt);
        } else {
            fijos.forEach(function(fijo) {
                var opt = document.createElement('option');
                // GASTOS_FIJOS ahora son objetos {descripcion, es_cuota, cuota_actual, total_cuotas}
                var desc = (typeof fijo === 'object') ? fijo.descripcion : fijo;
                opt.value = desc;
                if (typeof fijo === 'object' && fijo.es_cuota) {
                    opt.textContent = desc + ' (Cuota ' + (fijo.cuota_actual + 1) + '/' + fijo.total_cuotas + ')';
                } else {
                    opt.textContent = desc;
                }
                selectFijo.appendChild(opt);
            });
        }
        // Activar select, desactivar input
        inputDesc.disabled = true;
        inputDesc.style.display = 'none';
        selectFijo.disabled = false;
        selectFijo.style.display = '';
        // Ocultar sección cuotas (las cuotas se gestionan automáticamente al elegir del dropdown)
        if (seccionCuotasDesc) seccionCuotasDesc.style.display = 'none';
        if (checkboxCuotasDesc) checkboxCuotasDesc.checked = false;
        if (campoCuotasDesc) campoCuotasDesc.style.visibility = 'hidden';
        if (inputTotalCuotasDesc) inputTotalCuotasDesc.value = '';
    } else {
        // Restaurar input de texto libre
        inputDesc.disabled = false;
        inputDesc.style.display = '';
        selectFijo.disabled = true;
        selectFijo.style.display = 'none';
        // Mostrar sección cuotas si el tipo es gasto
        var selectTipoRef = document.getElementById('tipo');
        if (seccionCuotasDesc && selectTipoRef && selectTipoRef.value === 'gasto') {
            seccionCuotasDesc.style.display = '';
        }
    }
}


/*
================================================================================
FUNCIÓN: inicializarFechaHoy()
================================================================================
Propósito:
  En los formularios de nuevo gasto, pre-rellena el campo de fecha
  con la fecha de HOY. Así el usuario no tiene que escribirla si es
  un gasto de hoy.

  Esta función corre en el cliente (navegador), por eso usa
  new Date() que devuelve la fecha/hora del sistema del usuario.
  No usa el servidor para nada.
================================================================================
*/
function fmtFecha(iso) {
    // Convierte 'YYYY-MM-DD' → 'DD/MM/YYYY'
    var p = iso.split('-');
    return p[2] + '/' + p[1] + '/' + p[0];
}

function inicializarFechaHoy() {
    var campoFecha = document.querySelector('#fecha');
    if (!campoFecha) return;

    // Fecha por defecto: hoy (hora local)
    var today = new Date();
    var hoy = today.getFullYear() + '-' +
              String(today.getMonth() + 1).padStart(2, '0') + '-' +
              String(today.getDate()).padStart(2, '0');

    // Si el campo está vacío (formulario nuevo), usar hoy
    var fechaInicial = campoFecha.value || hoy;

    // Inicializar flatpickr con locale español y formato DD/MM/AAAA
    flatpickr(campoFecha, {
        locale: 'es',
        dateFormat: 'Y-m-d',      // valor interno (lo que se envía al servidor)
        altInput: true,
        altFormat: 'd/m/Y',       // formato visible: DD/MM/AAAA
        defaultDate: fechaInicial,
        allowInput: true
    });

    console.log('Fecha inicializada con flatpickr:', fechaInicial);
}


function inicializarFormatoMonto() {
    var display = document.getElementById('monto-display');
    var hidden  = document.getElementById('monto');
    if (!display) return;

    function formatear(str) {
        var limpio = str.replace(/[^0-9,]/g, '');
        var partes = limpio.split(',');
        if (partes.length > 2) partes = [partes[0], partes[1]];
        partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        return partes.join(',');
    }

    display.addEventListener('input', function() {
        var desdeElFinal = display.value.length - (display.selectionStart || display.value.length);
        display.value = formatear(display.value);
        var nuevaPos = Math.max(0, display.value.length - desdeElFinal);
        display.setSelectionRange(nuevaPos, nuevaPos);
        if (hidden) {
            hidden.value = display.value.replace(/\./g, '').replace(',', '.');
        }
    });

    // Formatear valor inicial (para la página de editar)
    if (hidden && hidden.value) {
        var n = parseFloat(hidden.value);
        if (!isNaN(n)) {
            var partes = hidden.value.split('.');
            var entero = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
            var decimal = (partes[1] && partes[1] !== '0') ? ',' + partes[1] : '';
            display.value = entero + decimal;
        }
    }
}


/*
================================================================================
FUNCIÓN: inicializarPersona()
================================================================================
Propósito:
  Recuerda la última persona seleccionada (Elías o Mari) usando localStorage,
  para que al volver a la página el selector ya venga pre-seleccionado.

  - Solo se aplica en formularios de nuevo gasto (index y nuevo.html).
  - En /editar/... se respeta el valor que viene pre-llenado del servidor.
  - Es por dispositivo/navegador (localStorage es local, no se sincroniza).
================================================================================
*/
function inicializarPersona() {
    var select = document.getElementById('persona');
    if (!select) return;

    // En la página de edición, el servidor ya envía el valor correcto → no sobreescribir
    if (!window.location.pathname.startsWith('/editar')) {
        var ultima = localStorage.getItem('ultima_persona');
        if (ultima) {
            select.value = ultima;
            console.log('Persona restaurada desde localStorage:', ultima);
        }
    }

    // Guardar cada vez que el usuario cambia la selección
    select.addEventListener('change', function() {
        localStorage.setItem('ultima_persona', select.value);
        console.log('Persona guardada en localStorage:', select.value);
    });
}


/*
================================================================================
FUNCIÓN: inicializarColoresDinamicos()
================================================================================
Propósito:
  Aplica colores de fondo dinámicos a los selects de Persona y Moneda del
  formulario rápido, reflejando visualmente la selección actual.

  Colores alineados con los badges de la tabla:
    Elías  → #3d7ab5 (azul,   badge-elias)
    Mari   → #9b59b6 (violeta, badge-mari)
    AR$    → #3d5a80 (azul primario)
    USD    → #1a6632 (verde oscuro, igual que badge-moneda-usd color)
================================================================================
*/
function inicializarColoresDinamicos() {
    var selectPersona      = document.getElementById('persona');
    var selectMoneda       = document.getElementById('moneda');
    var selectPersonaFinal = document.getElementById('persona_final');
    var selectMonedaFinal  = document.getElementById('moneda_final');

    /* Lee los colores de las variables CSS de la paleta — sin hardcodear */
    var cssVars = getComputedStyle(document.documentElement);
    var colorElias  = cssVars.getPropertyValue('--color-persona-elias').trim();
    var colorMari   = cssVars.getPropertyValue('--color-persona-mari').trim();
    var colorArs    = cssVars.getPropertyValue('--color-moneda-ars').trim();
    var colorUsd    = cssVars.getPropertyValue('--color-moneda-usd').trim();

    var coloresPersona = {
        elias: { bg: colorElias, text: 'white' },
        mari:  { bg: colorMari,  text: 'white' }
    };
    var coloresMoneda = {
        ars: { bg: colorArs, text: 'white' },
        usd: { bg: colorUsd, text: 'white' }
    };

    function aplicarColor(selectEl, mapa) {
        if (!selectEl) return;
        var c = mapa[selectEl.value];
        if (c) {
            selectEl.style.backgroundColor = c.bg;
            selectEl.style.color = c.text;
        }
    }

    // Persona y Moneda originales
    if (selectPersona) {
        selectPersona.addEventListener('change', function() { aplicarColor(selectPersona, coloresPersona); });
        aplicarColor(selectPersona, coloresPersona);
    }
    if (selectMoneda) {
        selectMoneda.addEventListener('change', function() { aplicarColor(selectMoneda, coloresMoneda); });
        aplicarColor(selectMoneda, coloresMoneda);
    }

    // Persona final y Moneda final (campos de Cambio)
    if (selectPersonaFinal) {
        selectPersonaFinal.addEventListener('change', function() { aplicarColor(selectPersonaFinal, coloresPersona); });
        aplicarColor(selectPersonaFinal, coloresPersona);
    }
    if (selectMonedaFinal) {
        selectMonedaFinal.addEventListener('change', function() { aplicarColor(selectMonedaFinal, coloresMoneda); });
        aplicarColor(selectMonedaFinal, coloresMoneda);
    }
}


/*
================================================================================
FUNCIÓN: resaltarNavActual()
================================================================================
Propósito:
  Resalta visualmente en el menú de navegación el enlace de la página
  que está actualmente abierta.
  Por ejemplo: si estás en /resumen, el botón "Resumen" del nav
  aparece resaltado/activo.

  Esto se hace comparando la URL actual con el href de cada enlace del nav.
================================================================================
*/
function resaltarNavActual() {
    /*
      window.location.pathname → la ruta actual de la URL.
      Ej: si la URL es http://localhost:5000/resumen, pathname = '/resumen'
    */
    var urlActual = window.location.pathname;

    /*
      querySelectorAll() → devuelve TODOS los elementos que coinciden.
      '.site-nav a' → todos los <a> dentro de un elemento con clase 'site-nav'
      Devuelve un NodeList (similar a un array).
    */
    var enlaces = document.querySelectorAll('.site-nav a');

    /*
      forEach() → itera sobre cada elemento del NodeList.
      Es el equivalente al "For Each" de Visual Basic.
    */
    enlaces.forEach(function(enlace) {
        /*
          enlace.getAttribute('href') → lee el atributo href del <a>
          Ej: para <a href="/resumen">, devuelve '/resumen'
        */
        var href = enlace.getAttribute('href');

        /*
          Comprobamos si la URL actual coincide con el href del enlace.
          Caso especial: '/' (inicio) solo resalta si la URL es exactamente '/'.
          Para otras páginas, chequeamos si la URL empieza con el href.
        */
        var esActual = (href === '/' && urlActual === '/') ||
                       (href !== '/' && urlActual.startsWith(href));

        if (esActual) {
            /*
              classList.add() → agrega una clase CSS al elemento.
              La clase 'nav-activo' está definida en style.css con un estilo
              visual diferente (fondo blanco translúcido, texto blanco).
            */
            enlace.classList.add('nav-activo');
            console.log('Nav activo:', href);
        }
    });
}


/*
================================================================================
FUNCIÓN: initFiltros()
================================================================================
Propósito:
  Maneja los botones de filtro sobre la tabla de movimientos.
  Filtra las filas del lado del cliente (sin recargar la página) según
  la persona y la moneda seleccionadas.

  Cada <tr> de la tabla tiene atributos data-persona y data-moneda.
  Cuando el usuario hace click en un botón de filtro, se ocultan las filas
  que no coinciden con el filtro activo.

  Los filtros de persona y moneda se combinan con AND:
  "Elías + AR$" muestra solo las filas donde persona=elias Y moneda=ars.
================================================================================
*/
function initSelectVista() {
    var selectVista = document.getElementById('select-vista');
    if (!selectVista) return;
    selectVista.addEventListener('change', function() {
        var url = new URL(window.location.href);
        url.searchParams.set('vista', this.value);
        window.location = url.toString();
    });
}

function initFiltros() {
    var botonesPersona = document.querySelectorAll('[data-filtro-persona]');
    var botonesMoneda  = document.querySelectorAll('[data-filtro-moneda]');

    // Si no hay botones de filtro en esta página, salimos
    if (botonesPersona.length === 0 && botonesMoneda.length === 0) return;

    var filtroPersona = 'todos';
    var filtroMoneda  = 'todos';
    var filtroSinCategoria = false;
    var filtroBusqueda = '';

    function aplicarFiltros() {
        var filas = document.querySelectorAll('#tabla-movimientos tbody tr');
        var visibles = 0;

        filas.forEach(function(fila) {
            var persona = fila.dataset.persona;
            var moneda  = fila.dataset.moneda;
            var categoria = fila.dataset.categoria;
            var descripcion = (fila.dataset.descripcion || '').toLowerCase();

            var okPersona   = (filtroPersona === 'todos' || persona === filtroPersona);
            var okMoneda    = (filtroMoneda  === 'todos' || moneda  === filtroMoneda);
            var okCategoria = (!filtroSinCategoria || categoria === 'No Definido');
            var okBusqueda  = (filtroBusqueda === '' || descripcion.indexOf(filtroBusqueda) !== -1);

            if (okPersona && okMoneda && okCategoria && okBusqueda) {
                fila.style.display = '';
                visibles++;
            } else {
                fila.style.display = 'none';
            }
        });

        console.log('Filtros aplicados — filas visibles:', visibles);
    }

    botonesPersona.forEach(function(btn) {
        btn.addEventListener('click', function() {
            botonesPersona.forEach(function(b) { b.classList.remove('filtro-activo'); });
            btn.classList.add('filtro-activo');
            filtroPersona = btn.dataset.filtroPersona;
            aplicarFiltros();
        });
    });

    botonesMoneda.forEach(function(btn) {
        btn.addEventListener('click', function() {
            botonesMoneda.forEach(function(b) { b.classList.remove('filtro-activo'); });
            btn.classList.add('filtro-activo');
            filtroMoneda = btn.dataset.filtroMoneda;
            aplicarFiltros();
        });
    });

    var btnSinCategoria = document.getElementById('btn-filtro-sin-categoria');
    if (btnSinCategoria) {
        btnSinCategoria.addEventListener('click', function() {
            filtroSinCategoria = !filtroSinCategoria;
            btnSinCategoria.classList.toggle('filtro-activo', filtroSinCategoria);
            aplicarFiltros();
        });
    }

    var inputBuscar = document.getElementById('input-buscar');
    if (inputBuscar) {
        inputBuscar.addEventListener('input', function() {
            filtroBusqueda = inputBuscar.value.trim().toLowerCase();
            aplicarFiltros();
        });
    }
}


/*
================================================================================
FUNCIÓN: initOrden()
================================================================================
  Maneja el toggle de ordenamiento de la tabla de movimientos.

  Dos modos:
  - "Carga ↓" (default): ordena por id DESC (el último cargado queda arriba)
  - "Fecha ↓": ordena por fecha DESC, luego id DESC (orden cronológico inverso)

  La función expone `ordenarTablaFn` globalmente para que initFormAjax pueda
  re-ordenar la tabla después de insertar una nueva fila vía AJAX.
================================================================================
*/
function initOrden() {
    var btnCarga = document.getElementById('btn-orden-carga');
    var btnFecha = document.getElementById('btn-orden-fecha');

    if (!btnCarga || !btnFecha) return;

    var ordenActual = 'carga';

    function ordenarTabla() {
        var tbody = document.querySelector('#tabla-movimientos tbody');
        if (!tbody) return;

        var filas = Array.from(tbody.querySelectorAll('tr'));

        filas.sort(function(a, b) {
            if (ordenActual === 'fecha') {
                // Primero por fecha DESC, luego por id DESC (desempate)
                var fa = a.dataset.fecha || '';
                var fb = b.dataset.fecha || '';
                if (fb !== fa) return fb.localeCompare(fa);
                return parseInt(b.dataset.id) - parseInt(a.dataset.id);
            } else {
                // Orden de carga: id DESC
                return parseInt(b.dataset.id) - parseInt(a.dataset.id);
            }
        });

        // Reinsertar filas en el nuevo orden
        filas.forEach(function(fila) { tbody.appendChild(fila); });
    }

    // Exponer para uso desde initFormAjax
    ordenarTablaFn = ordenarTabla;

    btnCarga.addEventListener('click', function() {
        if (ordenActual === 'carga') return;
        ordenActual = 'carga';
        btnCarga.classList.add('filtro-activo');
        btnFecha.classList.remove('filtro-activo');
        ordenarTabla();
    });

    btnFecha.addEventListener('click', function() {
        if (ordenActual === 'fecha') return;
        ordenActual = 'fecha';
        btnFecha.classList.add('filtro-activo');
        btnCarga.classList.remove('filtro-activo');
        ordenarTabla();
    });
}


/*
================================================================================
FUNCIÓN: initEdicionInline()
================================================================================
Propósito:
  Maneja la edición inline de movimientos directamente en la tabla.
  Al hacer click en "Editar", la fila se convierte en un formulario editable
  con botones "Guardar" y "Cancelar". No se navega a otra página.

  Usa delegación de eventos: en vez de poner un listener en cada botón,
  ponemos uno en la tabla y detectamos el click por la clase del botón.
  Así funciona aunque se recarguen filas dinámicamente.
================================================================================
*/
function initEdicionInline() {
    var tabla = document.getElementById('tabla-movimientos');
    if (!tabla) return;

    // Delegación de eventos en la tabla completa
    tabla.addEventListener('click', function(e) {
        var btn = e.target.closest('.btn-editar-fila');
        if (btn) {
            var fila = btn.closest('tr');
            activarEdicion(fila);
        }
    });
}


/*
================================================================================
FUNCIÓN: activarEdicion(fila)
================================================================================
Propósito:
  Transforma una fila de la tabla en un formulario editable inline.
  Lee los datos originales desde los data-attributes del <tr>,
  reemplaza el contenido de cada celda con un input o select,
  y agrega botones "Guardar" y "Cancelar".
================================================================================
*/
function activarEdicion(fila) {
    // Evitar activar edición si ya está en modo edición
    if (fila.classList.contains('fila-editando')) return;

    fila.classList.add('fila-editando');

    var id          = fila.dataset.id;
    var fecha       = fila.dataset.fecha;
    var descripcion = fila.dataset.descripcion;
    var persona     = fila.dataset.persona;
    var moneda      = fila.dataset.moneda;
    var tipo        = fila.dataset.tipo;
    var monto       = fila.dataset.monto;
    var categoria   = fila.dataset.categoria  || '';
    var costoEnvio  = fila.dataset.costoEnvio || '';

    // Guardar HTML original de cada celda para poder restaurar al cancelar
    // La tabla tiene 6 columnas: Fecha(0), Descripción(1), Info(2), Categoría(3), Monto(4), Acciones(5)
    var celdas = fila.querySelectorAll('td');
    var htmlOriginal = [];
    celdas.forEach(function(td) { htmlOriginal.push(td.innerHTML); });

    // Celda 0: fecha
    celdas[0].innerHTML =
        '<input type="date" class="input-inline" name="fecha" value="' + fecha + '">';

    // Celda 1: descripcion
    celdas[1].innerHTML =
        '<input type="text" class="input-inline input-descripcion" name="descripcion" ' +
        'value="' + descripcion.replace(/"/g, '&quot;') + '" maxlength="200">';

    // Celda 2: Info — persona + moneda + tipo (los 3 juntos)
    celdas[2].innerHTML =
        '<div class="inline-edit-info">' +
        '<select class="input-inline input-inline-mini" name="persona">' +
        '<option value="elias"' + (persona === 'elias' ? ' selected' : '') + '>Elías</option>' +
        '<option value="mari"'  + (persona === 'mari'  ? ' selected' : '') + '>Mari</option>' +
        '</select>' +
        '<select class="input-inline input-inline-mini" name="moneda">' +
        '<option value="ars"' + (moneda === 'ars' ? ' selected' : '') + '>AR$</option>' +
        '<option value="usd"' + (moneda === 'usd' ? ' selected' : '') + '>USD</option>' +
        '</select>' +
        '<select class="input-inline input-inline-mini" name="tipo">' +
        '<option value="gasto"'   + (tipo === 'gasto'   ? ' selected' : '') + '>Gasto</option>' +
        '<option value="ingreso"' + (tipo === 'ingreso' ? ' selected' : '') + '>Ingreso</option>' +
        '</select>' +
        '</div>';

    // Celda 3: categoría — opciones según el tipo actual
    var optsCategoria = (CATEGORIAS[tipo] || CATEGORIAS.gasto).map(function(c) {
        return '<option value="' + c + '"' + (c === categoria ? ' selected' : '') + '>' + c + '</option>';
    }).join('');
    celdas[3].innerHTML =
        '<select class="input-inline" name="categoria">' + optsCategoria + '</select>';

    // Celda 4: monto + sección de envío
    var envioVisible  = costoEnvio !== '';
    var envioDisplay  = (envioVisible && tipo === 'gasto') ? '' : 'none';
    var labelDisplay  = tipo === 'gasto' ? '' : 'none';
    celdas[4].innerHTML =
        '<input type="number" class="input-inline input-monto" name="monto" ' +
        'value="' + monto + '" step="0.01" min="0">' +
        '<label class="checkbox-envio-inline" style="display:' + labelDisplay + '">' +
        '<input type="checkbox" class="chk-envio-inline"' + (envioVisible ? ' checked' : '') + '> Incluye envío' +
        '</label>' +
        '<input type="number" class="input-inline input-envio-inline" name="costo_envio" ' +
        'value="' + costoEnvio + '" step="0.01" min="0" placeholder="0" style="display:' + envioDisplay + '">';

    // Celda 5: botones guardar/cancelar
    celdas[5].innerHTML =
        '<button type="button" class="btn btn-guardar-inline" title="Guardar">✓</button>' +
        '<button type="button" class="btn btn-cancelar-inline" title="Cancelar">✕</button>';

    // Cuando cambia el tipo → actualizar categorías y visibilidad del envío
    var selectTipoInline = celdas[2].querySelector('select[name="tipo"]');
    var selectCatInline  = celdas[3].querySelector('select');
    var labelEnvioInline = celdas[4].querySelector('.checkbox-envio-inline');
    var chkEnvioInline   = celdas[4].querySelector('.chk-envio-inline');
    var inputEnvioInline = celdas[4].querySelector('.input-envio-inline');

    selectTipoInline.addEventListener('change', function() {
        llenarSelectCategorias(selectCatInline, selectTipoInline.value, null);
        var esGasto = selectTipoInline.value === 'gasto';
        labelEnvioInline.style.display = esGasto ? '' : 'none';
        if (!esGasto) {
            chkEnvioInline.checked = false;
            inputEnvioInline.style.display = 'none';
            inputEnvioInline.value = '';
        }
    });

    chkEnvioInline.addEventListener('change', function() {
        inputEnvioInline.style.display = chkEnvioInline.checked ? '' : 'none';
        if (!chkEnvioInline.checked) inputEnvioInline.value = '';
    });

    celdas[5].querySelector('.btn-guardar-inline').addEventListener('click', function() {
        guardarEdicion(fila, id);
    });

    celdas[5].querySelector('.btn-cancelar-inline').addEventListener('click', function() {
        cancelarEdicion(fila, htmlOriginal);
    });
}


/*
================================================================================
FUNCIÓN: guardarEdicion(fila, id)
================================================================================
Propósito:
  Recolecta los valores de los inputs de la fila en edición y los envía
  via fetch (POST) a /editar/<id>. Si el servidor responde OK, recarga la
  página para reflejar los cambios actualizados (incluyendo saldos).

  fetch() es la API moderna del navegador para hacer peticiones HTTP
  sin recargar la página (equivalente a axios, XHR, etc.).
================================================================================
*/
function guardarEdicion(fila, id) {
    var datos = new FormData();
    fila.querySelectorAll('.input-inline').forEach(function(input) {
        datos.append(input.name, input.value);
    });

    // Deshabilitar botones mientras se guarda
    fila.querySelectorAll('.btn-guardar-inline, .btn-cancelar-inline').forEach(function(b) {
        b.disabled = true;
    });

    fetch('/editar/' + id, {
        method: 'POST',
        body: datos
    })
    .then(function(response) {
        // Flask redirige con 302, fetch lo sigue automáticamente → response.ok = true
        if (response.ok) {
            window.location.reload();
        } else {
            throw new Error('Respuesta inesperada: ' + response.status);
        }
    })
    .catch(function(err) {
        console.error('Error al guardar edición:', err);
        alert('Error al guardar los cambios. Revisá la consola para más detalles.');
        fila.querySelectorAll('.btn-guardar-inline, .btn-cancelar-inline').forEach(function(b) {
            b.disabled = false;
        });
    });
}


/*
================================================================================
FUNCIÓN: cancelarEdicion(fila, htmlOriginal)
================================================================================
Propósito:
  Restaura el HTML original de cada celda de la fila, volviendo al
  estado de visualización normal sin cambios.
================================================================================
*/
function cancelarEdicion(fila, htmlOriginal) {
    fila.classList.remove('fila-editando');
    var celdas = fila.querySelectorAll('td');
    celdas.forEach(function(td, i) {
        td.innerHTML = htmlOriginal[i];
    });
}


/*
================================================================================
HELPERS DE FORMATO — replican en JS los filtros fmt_ars / fmt_usd de Python
================================================================================
Se usan para formatear el monto en la nueva fila y en el toast, sin necesidad
de recargar la página ni de llamar al servidor.
================================================================================
*/
function fmtArs(valor) {
    var signo  = valor < 0 ? '-' : '';
    var entero = Math.round(Math.abs(valor));
    var str    = entero.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return '$ ' + signo + str;
}

function fmtUsd(valor) {
    var signo    = valor < 0 ? '-' : '';
    var abs      = Math.abs(valor);
    var partes   = abs.toFixed(2).split('.');
    var entero   = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return 'USD ' + signo + entero + ',' + partes[1];
}


/*
================================================================================
FUNCIÓN: actualizarSaldos(saldos)
================================================================================
Actualiza el texto y la clase CSS de los 4 elementos de saldo en las tarjetas,
usando los valores recibidos en el JSON de respuesta AJAX.
================================================================================
*/
function actualizarSaldos(saldos) {
    var mapa = {
        'elias_ars': { id: 'saldo-elias-ars', fmt: fmtArs },
        'elias_usd': { id: 'saldo-elias-usd', fmt: fmtUsd },
        'mari_ars':  { id: 'saldo-mari-ars',  fmt: fmtArs },
        'mari_usd':  { id: 'saldo-mari-usd',  fmt: fmtUsd },
    };

    Object.keys(mapa).forEach(function(clave) {
        var el = document.getElementById(mapa[clave].id);
        if (!el) return;
        var valor = saldos[clave] || 0;
        el.textContent = mapa[clave].fmt(valor);
        el.className = 'saldo-monto ' + (valor < 0 ? 'saldo-negativo' : 'saldo-positivo');
    });

    // Actualizar columna Total
    var totalArs = (saldos['elias_ars'] || 0) + (saldos['mari_ars'] || 0);
    var totalUsd = (saldos['elias_usd'] || 0) + (saldos['mari_usd'] || 0);
    var elTotalArs = document.getElementById('saldo-total-ars');
    var elTotalUsd = document.getElementById('saldo-total-usd');
    if (elTotalArs) {
        elTotalArs.textContent = fmtArs(totalArs);
        elTotalArs.className = 'saldo-monto ' + (totalArs < 0 ? 'saldo-negativo' : 'saldo-positivo');
    }
    if (elTotalUsd) {
        elTotalUsd.textContent = fmtUsd(totalUsd);
        elTotalUsd.className = 'saldo-monto ' + (totalUsd < 0 ? 'saldo-negativo' : 'saldo-positivo');
    }
}


/*
================================================================================
FUNCIÓN: crearFilaMovimiento(mov)
================================================================================
Genera el <tr> HTML de un movimiento para insertarlo al inicio del tbody,
replicando la estructura que Jinja2 produce en el servidor.
================================================================================
*/
function crearFilaMovimiento(mov) {
    var personaNombre = mov.persona === 'elias' ? 'Elías' : 'Mari';
    var monedaLabel   = mov.moneda  === 'ars'   ? 'AR$'   : 'USD';
    var tipoLabel     = mov.tipo    === 'ingreso'? 'Ingreso' : 'Gasto';

    var factorAplicado = mov.factor_aplicado != null ? mov.factor_aplicado : null;
    var montoEfectivo  = factorAplicado !== null ? mov.monto * factorAplicado : mov.monto;
    var montoFmt       = mov.moneda === 'ars' ? fmtArs(montoEfectivo) : fmtUsd(montoEfectivo);

    var badgeEnvio = '';
    if (factorAplicado !== null) {
        var brutoFmt = mov.moneda === 'ars' ? fmtArs(mov.monto) : fmtUsd(mov.monto);
        badgeEnvio = '<span class="badge-envio">Sueldo: ' + brutoFmt + ' × ' + factorAplicado + '</span>';
    } else if (mov.costo_envio) {
        var envioFmt = mov.moneda === 'ars' ? fmtArs(mov.costo_envio) : fmtUsd(mov.costo_envio);
        badgeEnvio = '<span class="badge-envio">📦 ' + envioFmt + '</span>';
    }

    var badgeCuota = '';
    if (mov.cuota_numero) {
        badgeCuota = '<span class="badge-cuota">Cuota ' + mov.cuota_numero + '/' + mov.cuota_total + '</span>';
    }

    // Escapar descripción para uso en atributo HTML y en celda
    var descAttr  = mov.descripcion.replace(/&/g,'&amp;').replace(/"/g,'&quot;');
    var descTexto = mov.descripcion.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

    var tr = document.createElement('tr');
    tr.setAttribute('data-persona',    mov.persona);
    tr.setAttribute('data-moneda',     mov.moneda);
    tr.setAttribute('data-id',         mov.id);
    tr.setAttribute('data-fecha',      mov.fecha);
    tr.setAttribute('data-descripcion',descAttr);
    tr.setAttribute('data-tipo',       mov.tipo);
    tr.setAttribute('data-monto',      mov.monto);
    tr.setAttribute('data-categoria',  mov.categoria || '');
    tr.setAttribute('data-costo-envio',mov.costo_envio || '');

    tr.innerHTML =
        '<td data-label="Fecha">' + fmtFecha(mov.fecha) + '</td>' +
        '<td class="col-descripcion" data-label="Descripción">' + descTexto + '</td>' +
        '<td class="col-info" data-label="Info">' +
            '<span class="badge-persona badge-' + mov.persona + '">' + personaNombre + '</span> ' +
            '<span class="badge-moneda badge-moneda-' + mov.moneda + '">' + monedaLabel + '</span> ' +
            '<span class="badge-tipo badge-' + mov.tipo + '">' + tipoLabel + '</span>' +
        '</td>' +
        '<td data-label="Categoría">' + (mov.categoria || '—') + '</td>' +
        '<td class="col-monto" data-label="Monto">' + montoFmt + badgeEnvio + badgeCuota + '</td>' +
        '<td class="col-acciones">' +
            '<button type="button" class="btn btn-editar btn-editar-fila" title="Editar">✎</button>' +
            '<form action="/eliminar/' + mov.id + '" method="POST" class="form-inline">' +
                '<button type="button" class="btn btn-borrar" title="Eliminar" onclick="mostrarModalBorrado(this.closest(\'form\'))">✕</button>' +
            '</form>' +
        '</td>';

    return tr;
}


/*
================================================================================
FUNCIÓN: mostrarToast(mov)
================================================================================
Muestra una notificación tipo "toast" en la esquina superior derecha con los
datos del movimiento recién cargado. Se apila si se llama varias veces seguidas.
Se desvanece y se elimina automáticamente a los 3 segundos.
================================================================================
*/
function mostrarToast(mov) {
    var container = document.getElementById('toast-container');
    if (!container) return;

    var tipoLabel     = mov.tipo    === 'ingreso' ? 'Ingreso' : 'Gasto';
    var personaNombre = mov.persona === 'elias'   ? 'Elías'   : 'Mari';
    var monedaLabel   = mov.moneda  === 'ars'     ? 'AR$'     : 'USD';
    var montoFmt      = mov.moneda  === 'ars'     ? fmtArs(mov.monto) : fmtUsd(mov.monto);
    var categoriaLabel = mov.categoria || 'No Definido';

    var toast = document.createElement('div');
    toast.className = 'toast toast-' + mov.tipo;
    toast.innerHTML =
        '<span class="toast-icono">✓</span>' +
        '<span class="toast-texto">' +
            '<strong>' + tipoLabel + ' cargado</strong> — ' +
            categoriaLabel + ' · ' + montoFmt + ' · ' + personaNombre + ' · ' + monedaLabel +
        '</span>';

    container.appendChild(toast);

    // Entrada: esperar un tick para que la transición CSS se active
    setTimeout(function() { toast.classList.add('toast-visible'); }, 10);

    // Salida a los 3 segundos
    setTimeout(function() {
        toast.classList.remove('toast-visible');
        toast.classList.add('toast-saliendo');
        setTimeout(function() {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 300);
    }, 3000);
}


/*
================================================================================
FUNCIÓN: initFormAjax()
================================================================================
Intercepta el submit del formulario rápido y lo envía via fetch() sin recargar
la página. Al recibir la respuesta JSON del servidor:
  1. Actualiza los 4 valores de saldo en las tarjetas
  2. Inserta la nueva fila al inicio de la tabla de movimientos
  3. Muestra el toast de confirmación
  4. Limpia el formulario, conservando persona y moneda
================================================================================
*/
function initFormAjax() {
    var form = document.querySelector('.form-rapido');
    if (!form) return;

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        var btnAgregar = form.querySelector('.btn-guardar-rapido');
        if (btnAgregar) btnAgregar.disabled = true;

        var datos = new FormData(form);

        fetch('/agregar', {
            method: 'POST',
            body: datos,
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function(res) {
            if (!res.ok) throw new Error('HTTP ' + res.status);
            return res.json();
        })
        .then(function(data) {
            if (!data.ok) throw new Error('El servidor devolvió ok=false');

            // Redirigir preservando el mes activo
            var mes = new URLSearchParams(window.location.search).get('mes') || '';
            window.location.href = mes ? '/?mes=' + mes : '/';
        })
        .catch(function(err) {
            console.error('Error AJAX al agregar:', err);
            alert('Error al agregar el movimiento. Recargá la página e intentá de nuevo.');
        })
        .finally(function() {
            if (btnAgregar) btnAgregar.disabled = false;
        });
    });
}
