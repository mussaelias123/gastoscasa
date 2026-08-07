/*
================================================================================
ARCHIVO: static/grafico.js
================================================================================
"Explorar mis datos": el gráfico y la tabla que viven adentro del Resumen.

QUÉ ES. Un gráfico VACÍO que no sabe de leche: la mamá elige qué variable va en
el eje horizontal y cuál en el vertical, y él dibuja lo que corresponda. El
primer uso es mirar si la hora a la que se extrae tiene que ver con cuánto sale,
pero el mismo gráfico sirve para cualquier otro cruce.

CÓMO SE LE AGREGA UNA VARIABLE. Un renglón en EJES_X o en EJES_Y. Nada más: el
desplegable, el agrupado, el tipo de gráfico, los rótulos y la tabla salen solos
de esa definición. Esa es toda la gracia de tenerlo separado.

DE DÓNDE SALEN LOS DATOS. De `DATOS.muestras`, que arma el servidor
(logica._lac_muestras). Cada muestra es UNA extracción real:

    { id, fecha: '2026-08-05', hora: '07:30' | null, ml: 120,
      dia_vida: 84 | null, mes_vida: 3 | null, dia_semana: 0..6 }

Acá NO se decide qué cuenta como extracción —eso ya viene resuelto del
servidor, que es donde vive esa regla— ni se calcula la edad del bebé. Acá solo
se agrupa y se dibuja.

POR QUÉ SIN LIBRERÍA. La app se instala en el teléfono y tiene que abrir sin
conexión: sumar 200 KB de una librería de gráficos para dibujar puntos, barras y
una línea no se paga. El SVG se arma a mano, igual que los íconos de la app.

LOS COLORES van por CSS (clases lac-gr-*), nunca escritos acá: así el gráfico
acompaña el modo día y el modo noche sin una sola línea extra.

Se acopla a lactancia.js por DOS líneas: init() le presta sus ayudantes y
render() le pasa los datos frescos después de cada carga o cierre.
================================================================================
*/

window.LAC_GRAFICO = (function () {
    'use strict';

    // ── Ayudantes prestados por lactancia.js (init los reemplaza) ────────────
    var T = function (s) { return s; };
    var fmtMl = function (n) { return (Number(n) || 0) + ' ml'; };
    var esc = function (s) { return String(s); };
    var fmtFechaCorta = function (s) { return String(s); };

    var DATOS = null;
    var armado = false;                       // ¿ya se dibujaron los desplegables?
    var MEMORIA = 'lac_grafico_ejes';         // la última combinación elegida
    var selX = 'hora';
    var selY = 'ml_muestra';

    function $(id) { return document.getElementById(id); }

    function pad2(n) { return String(n).padStart(2, '0'); }

    // ── Fechas como número ───────────────────────────────────────────────────
    // Para poner una fecha en un eje hace falta un número. Se usa el día
    // corrido desde 1970 (en UTC a propósito: así el número de un día no cambia
    // según el huso horario ni el horario de verano).
    function indiceDeFecha(iso) {
        var p = String(iso || '').split('-');
        if (p.length !== 3) return null;
        return Math.floor(Date.UTC(Number(p[0]), Number(p[1]) - 1, Number(p[2])) / 86400000);
    }

    function fechaDeIndice(n) {
        var d = new Date(n * 86400000);
        return d.getUTCFullYear() + '-' + pad2(d.getUTCMonth() + 1) + '-' + pad2(d.getUTCDate());
    }

    function horaDecimal(m) {
        if (!m.hora) return null;
        var p = String(m.hora).split(':');
        if (p.length < 2) return null;
        return Number(p[0]) + Number(p[1]) / 60;
    }

    // ── Las variables del eje horizontal ─────────────────────────────────────
    // `tipo` decide cómo se dibuja: 'numero' va sobre una regla continua (los
    // huecos se ven, que es justamente lo que interesa en las horas), y
    // 'categoria' va en casilleros iguales, uno al lado del otro.
    //   grupo(m)  → el número por el que se junta (null = esta muestra no aplica)
    //   punto(m)  → dónde cae en la nube de puntos (por defecto, el grupo)
    //   etiqueta  → cómo se escribe ese grupo en el eje y en la tabla
    var EJES_X = [
        {
            clave: 'hora', tipo: 'numero',
            label: function () { return T('Hora de extracción'); },
            grupo: function (m) { var h = horaDecimal(m); return h === null ? null : Math.floor(h); },
            punto: function (m) { return horaDecimal(m); },
            etiqueta: function (g) { return pad2(g) + ' h'; },
            dominio: function () { return [0, 24]; },
            marcas: [0, 6, 12, 18, 24]
        },
        {
            clave: 'momento', tipo: 'categoria',
            label: function () { return T('Momento del día'); },
            grupo: function (m) {
                var h = horaDecimal(m);
                if (h === null) return null;
                return h < 6 ? 0 : h < 12 ? 1 : h < 18 ? 2 : 3;
            },
            etiqueta: function (g) {
                return [T('Madrugada'), T('Mañana'), T('Tarde'), T('Noche')][g] || '';
            },
            // Debajo del eje entra "Mañana", pero en la frase que explica el
            // gráfico hace falta "la mañana": si no, quedan cosas como "Donde
            // más sale: Mañana".
            etiquetaLarga: function (g) {
                return [T('la madrugada'), T('la mañana'),
                        T('la tarde'), T('la noche')][g] || '';
            },
            categorias: function () { return [0, 1, 2, 3]; }
        },
        {
            clave: 'fecha', tipo: 'numero',
            label: function () { return T('Fecha de extracción'); },
            grupo: function (m) { return indiceDeFecha(m.fecha); },
            etiqueta: function (g) { return fmtFechaCorta(fechaDeIndice(g)); }
        },
        {
            clave: 'dia_semana', tipo: 'categoria',
            label: function () { return T('Día de la semana'); },
            grupo: function (m) { return m.dia_semana; },
            etiqueta: function (g) {
                return [T('lun'), T('mar'), T('mié'), T('jue'),
                        T('vie'), T('sáb'), T('dom')][g] || '';
            },
            etiquetaLarga: function (g) {
                return [T('los lunes'), T('los martes'), T('los miércoles'),
                        T('los jueves'), T('los viernes'), T('los sábados'),
                        T('los domingos')][g] || '';
            },
            categorias: function () { return [0, 1, 2, 3, 4, 5, 6]; }
        },
        {
            clave: 'dia_vida', tipo: 'numero', requiereBebe: true,
            label: function () { return T('Día de vida del bebé'); },
            grupo: function (m) { return m.dia_vida === null ? null : m.dia_vida; },
            etiqueta: function (g) { return T('día {n}', { n: g }); }
        },
        {
            clave: 'mes_vida', tipo: 'categoria', requiereBebe: true,
            label: function () { return T('Mes de vida del bebé'); },
            grupo: function (m) { return m.mes_vida === null ? null : m.mes_vida; },
            etiqueta: function (g) { return T('mes {n}', { n: g }); },
            etiquetaLarga: function (g) { return T('el mes {n}', { n: g }); }
            // Sin `categorias`: los meses que haya en los datos, y nada más.
        }
    ];

    // ── Las variables del eje vertical ───────────────────────────────────────
    // `modo` decide si cada muestra va suelta (una bolsita = un punto) o si el
    // grupo se resume en un solo número.
    var EJES_Y = [
        {
            clave: 'ml_muestra', modo: 'muestra',
            label: function () { return T('Ml de cada extracción'); },
            unidad: function () { return T('ml'); },
            fmt: function (n) { return fmtMl(n); }
        },
        {
            clave: 'ml_total', modo: 'suma',
            label: function () { return T('Ml extraídos (total)'); },
            unidad: function () { return T('ml'); },
            fmt: function (n) { return fmtMl(n); }
        },
        {
            clave: 'ml_promedio', modo: 'promedio',
            label: function () { return T('Ml por extracción (promedio)'); },
            unidad: function () { return T('ml'); },
            fmt: function (n) { return fmtMl(n); }
        },
        {
            clave: 'cantidad', modo: 'cantidad',
            label: function () { return T('Cantidad de extracciones'); },
            unidad: function () { return T('extracciones'); },
            fmt: function (n) { return String(n); }
        }
    ];

    function buscarEje(lista, clave) {
        for (var i = 0; i < lista.length; i++) {
            if (lista[i].clave === clave) return lista[i];
        }
        return lista[0];
    }

    function hayBebe() {
        return !!(DATOS && DATOS.bebe && DATOS.bebe.fecha_nacimiento);
    }

    // ── Agrupar ──────────────────────────────────────────────────────────────
    function agrupar(vx, muestras) {
        var mapa = {};
        muestras.forEach(function (m) {
            var g = vx.grupo(m);
            if (g === null || g === undefined || isNaN(g)) return;
            if (!mapa[g]) mapa[g] = { clave: Number(g), n: 0, suma: 0 };
            mapa[g].n++;
            mapa[g].suma += Number(m.ml) || 0;
        });
        // En las variables con casilleros fijos (momento del día, día de la
        // semana) se muestran TODOS, aunque estén vacíos: un lunes sin ninguna
        // extracción es información, y si el casillero desapareciera parecería
        // que la semana tiene seis días.
        if (vx.categorias) {
            vx.categorias().forEach(function (c) {
                if (!mapa[c]) mapa[c] = { clave: Number(c), n: 0, suma: 0 };
            });
        }
        var lista = Object.keys(mapa).map(function (k) { return mapa[k]; });
        lista.sort(function (a, b) { return a.clave - b.clave; });
        lista.forEach(function (g) {
            g.promedio = g.n ? Math.round(g.suma / g.n) : 0;
        });
        return lista;
    }

    function valorDe(grupo, vy) {
        if (vy.modo === 'cantidad') return grupo.n;
        if (vy.modo === 'promedio') return grupo.promedio;
        return grupo.suma;
    }

    // ── Qué gráfico corresponde a cada par ───────────────────────────────────
    // Toda la regla, en cuatro renglones:
    //   una bolsita = un punto            → nube de puntos
    //   un número por día del calendario  → línea (se lee como evolución)
    //   el resto                          → barras
    function tipoGrafico(vx, vy) {
        if (vy.modo === 'muestra') return 'puntos';
        if (vx.clave === 'fecha') return 'linea';
        return 'barras';
    }

    // ── Escala vertical con números redondos ─────────────────────────────────
    function escalaLinda(max) {
        if (!(max > 0)) return { max: 10, paso: 5 };
        var bruto = max / 4;
        var mag = Math.pow(10, Math.floor(Math.log(bruto) / Math.LN10));
        var norm = bruto / mag;
        var paso = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
        // Nunca menos de 1: acá todo se cuenta en enteros (mililitros y
        // extracciones). Sin este piso, una mamá que recién empieza —con una
        // sola extracción por día— vería el eje repitiendo "0, 1, 1".
        paso = Math.max(paso, 1);
        return { max: Math.ceil(max / paso) * paso, paso: paso };
    }

    // Una pizca de corrimiento horizontal para que dos bolsitas de la misma
    // categoría y el mismo volumen no queden una tapando a la otra. Sale del id
    // (no del azar) para que el punto no salte de lugar en cada redibujado.
    function corrimiento(m) {
        return ((Number(m.id) * 37) % 101) / 101 - 0.5;
    }

    // ── El dibujo ────────────────────────────────────────────────────────────
    var W = 440, H = 250;
    var MAR = { arriba: 22, derecha: 12, abajo: 34, izq: 46 };
    var AN = W - MAR.izq - MAR.derecha;
    var AL = H - MAR.arriba - MAR.abajo;

    function texto(x, y, s, clase, anclaje) {
        return '<text class="' + clase + '" x="' + x + '" y="' + y + '"' +
            (anclaje ? ' text-anchor="' + anclaje + '"' : '') + '>' + esc(s) + '</text>';
    }

    function dibujarSvg(vx, vy, muestras, grupos, forma) {
        // ── Escala vertical
        var maxY = 0;
        if (forma === 'puntos') {
            muestras.forEach(function (m) { if (m.ml > maxY) maxY = m.ml; });
        } else {
            grupos.forEach(function (g) {
                var v = valorDe(g, vy);
                if (v > maxY) maxY = v;
            });
        }
        var escala = escalaLinda(maxY);
        function y(v) { return MAR.arriba + AL - (v / escala.max) * AL; }

        // ── Escala horizontal
        var esBanda = vx.tipo === 'categoria';
        var banda = esBanda ? AN / Math.max(grupos.length, 1) : 0;
        var d0 = 0, d1 = 1;
        if (!esBanda) {
            if (vx.dominio) {
                var d = vx.dominio();
                d0 = d[0]; d1 = d[1];
            } else {
                d0 = grupos[0].clave;
                d1 = grupos[grupos.length - 1].clave;
                if (d1 - d0 < 1) { d0 -= 1; d1 += 1; }
                else { d0 -= 0.5; d1 += 0.5; }
            }
        }
        function x(v) { return MAR.izq + ((v - d0) / (d1 - d0)) * AN; }
        function xBanda(i) { return MAR.izq + (i + 0.5) * banda; }

        var s = '';

        // ── Reglas horizontales y números de la izquierda
        for (var v = 0; v <= escala.max + 0.0001; v += escala.paso) {
            var yy = y(v);
            s += '<line class="lac-gr-guia" x1="' + MAR.izq + '" y1="' + yy +
                 '" x2="' + (MAR.izq + AN) + '" y2="' + yy + '"/>';
            s += texto(MAR.izq - 7, yy + 4, Math.round(v), 'lac-gr-rotulo', 'end');
        }

        // Unidad del eje vertical, arriba a la izquierda (más corto que un
        // título rotado, y en el celular se lee mejor).
        s += texto(2, 12, vy.unidad(), 'lac-gr-unidad');

        // ── El dato
        if (forma === 'puntos') {
            muestras.forEach(function (m) {
                var px;
                if (esBanda) {
                    var i = indiceDeGrupo(grupos, vx.grupo(m));
                    if (i < 0) return;
                    px = xBanda(i) + corrimiento(m) * banda * 0.6;
                } else {
                    var val = vx.punto ? vx.punto(m) : vx.grupo(m);
                    if (val === null) return;
                    px = x(val);
                }
                s += '<circle class="lac-gr-punto" cx="' + px.toFixed(1) + '" cy="' +
                     y(m.ml).toFixed(1) + '" r="3.6"><title>' +
                     esc(fmtMl(m.ml) + ' · ' + vx.etiqueta(vx.grupo(m))) + '</title></circle>';
            });
        } else if (forma === 'linea') {
            var puntos = grupos.map(function (g) {
                return x(g.clave).toFixed(1) + ',' + y(valorDe(g, vy)).toFixed(1);
            });
            s += '<polyline class="lac-gr-linea" points="' + puntos.join(' ') + '"/>';
            // Los nodos solo si son pocos: con 200 días serían una mancha.
            if (grupos.length <= 60) {
                grupos.forEach(function (g) {
                    s += '<circle class="lac-gr-nodo" cx="' + x(g.clave).toFixed(1) +
                         '" cy="' + y(valorDe(g, vy)).toFixed(1) + '" r="2.6"><title>' +
                         esc(vx.etiqueta(g.clave) + ': ' + vy.fmt(valorDe(g, vy))) +
                         '</title></circle>';
                });
            }
        } else {
            var ancho = esBanda ? banda * 0.62
                                : Math.max((AN / (d1 - d0)) * 0.8, 1.5);
            grupos.forEach(function (g, i) {
                var val = valorDe(g, vy);
                if (!val) return;
                var cx = esBanda ? xBanda(i) : x(g.clave);
                var alto = MAR.arriba + AL - y(val);
                s += '<rect class="lac-gr-barra" x="' + (cx - ancho / 2).toFixed(1) +
                     '" y="' + y(val).toFixed(1) + '" width="' + ancho.toFixed(1) +
                     '" height="' + Math.max(alto, 1).toFixed(1) + '" rx="1.5"><title>' +
                     esc(vx.etiqueta(g.clave) + ': ' + vy.fmt(val)) + '</title></rect>';
            });
        }

        // ── Ejes
        s += '<line class="lac-gr-eje" x1="' + MAR.izq + '" y1="' + (MAR.arriba + AL) +
             '" x2="' + (MAR.izq + AN) + '" y2="' + (MAR.arriba + AL) + '"/>';
        s += '<line class="lac-gr-eje" x1="' + MAR.izq + '" y1="' + MAR.arriba +
             '" x2="' + MAR.izq + '" y2="' + (MAR.arriba + AL) + '"/>';

        // ── Rótulos de abajo
        var baseY = MAR.arriba + AL + 15;
        if (esBanda) {
            // Con muchos casilleros se saltean rótulos para que no se pisen.
            var salto = Math.ceil(grupos.length / 8);
            grupos.forEach(function (g, i) {
                if (i % salto) return;
                s += texto(xBanda(i), baseY, vx.etiqueta(g.clave), 'lac-gr-rotulo', 'middle');
            });
        } else {
            var marcas = vx.marcas || repartir(d0, d1, 5);
            marcas.forEach(function (mk) {
                if (mk < d0 || mk > d1) return;
                s += texto(x(mk), baseY, vx.etiqueta(mk), 'lac-gr-rotulo', 'middle');
            });
        }
        s += texto(MAR.izq + AN / 2, H - 3, vx.label(), 'lac-gr-titulo-eje', 'middle');

        return '<svg class="lac-gr-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" ' +
            'aria-label="' + esc(vy.label() + ' ' + T('según') + ' ' + vx.label()) + '">' +
            s + '</svg>';
    }

    function indiceDeGrupo(grupos, clave) {
        for (var i = 0; i < grupos.length; i++) {
            if (grupos[i].clave === Number(clave)) return i;
        }
        return -1;
    }

    // Números enteros repartidos parejo entre dos extremos, sin repetidos.
    function repartir(d0, d1, cuantos) {
        var out = [], visto = {};
        for (var i = 0; i <= cuantos; i++) {
            var v = Math.round(d0 + (d1 - d0) * (i / cuantos));
            if (!visto[v]) { visto[v] = 1; out.push(v); }
        }
        return out;
    }

    // ── La lectura en castellano ─────────────────────────────────────────────
    // Es lo que de verdad contesta la pregunta: el gráfico muestra, esta línea
    // dice. Con pocas extracciones NO afirma nada — mejor callarse que hacerle
    // creer a una mamá que encontró un patrón donde hay tres datos sueltos.
    var MINIMO_TOTAL = 8;
    var MINIMO_GRUPO = 3;

    // Extracciones por día: cuántas hubo dividido los días en que hubo alguna.
    function porDia(lista) {
        var dias = {};
        lista.forEach(function (m) { dias[m.fecha] = 1; });
        return lista.length / Math.max(Object.keys(dias).length, 1);
    }

    // Un decimal, con la coma o el punto que use el teléfono de cada mamá.
    function dec(n) {
        return Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });
    }

    function lectura(vx, vy, muestras) {
        if (muestras.length < MINIMO_TOTAL) {
            return T('Todavía son pocas extracciones para ver una relación. Seguí cargando y esto se va a ir afinando.');
        }
        var porCantidad = vy.modo === 'cantidad';

        // Con muchos grupos (fechas, días de vida) comparar uno contra uno no
        // dice nada: ahí se mira el antes y el después.
        var vAgrupar = vx;
        if (vx.clave === 'hora') vAgrupar = buscarEje(EJES_X, 'momento');
        var grupos = agrupar(vAgrupar, muestras).filter(function (g) { return g.n > 0; });

        if (grupos.length > 12 || grupos.length < 2) return mitades(muestras, porCantidad);

        var mejor = null;
        grupos.forEach(function (g) {
            if (g.n < MINIMO_GRUPO) return;
            var valor = porCantidad ? g.n : g.promedio;
            if (!mejor || valor > mejor.valor) mejor = { g: g, valor: valor };
        });
        if (!mejor) return mitades(muestras, porCantidad);

        var restoN = 0, restoSuma = 0;
        grupos.forEach(function (g) {
            if (g === mejor.g) return;
            restoN += g.n;
            restoSuma += g.suma;
        });
        if (restoN < MINIMO_GRUPO) return mitades(muestras, porCantidad);

        // El grupo va después de dos puntos y no metido en la oración: así la
        // misma frase sirve para "la mañana", "los martes" y "el mes 4" sin
        // pelearse con el género ni con el singular y el plural.
        var nombre = (vAgrupar.etiquetaLarga || vAgrupar.etiqueta)(mejor.g.clave);
        if (porCantidad) {
            // Contra el PROMEDIO de las demás, no contra la suma: "21 contra 87"
            // compararía un día con seis y siempre parecería poco.
            var otras = Math.max(grupos.length - 1, 1);
            return T('Donde más te extraés: {grupo}, con {n} extracciones, contra {resto} en promedio en las demás.',
                     { grupo: nombre, n: mejor.g.n, resto: Math.round(restoN / otras) });
        }
        return T('Donde más sale: {grupo}, con {prom} por extracción, contra {resto} en el resto. ({n} de {total} extracciones)',
                 { grupo: nombre, prom: fmtMl(mejor.g.promedio),
                   resto: fmtMl(Math.round(restoSuma / restoN)),
                   n: mejor.g.n, total: muestras.length });
    }

    function mitades(muestras, porCantidad) {
        var orden = muestras.slice().sort(function (a, b) {
            return (a.fecha + (a.hora || '')) < (b.fecha + (b.hora || '')) ? -1 : 1;
        });
        var corte = Math.floor(orden.length / 2);
        var prim = orden.slice(0, corte), seg = orden.slice(corte);
        if (prim.length < MINIMO_GRUPO || seg.length < MINIMO_GRUPO) {
            return T('Todavía son pocas extracciones para ver una relación. Seguí cargando y esto se va a ir afinando.');
        }

        // Con el eje vertical en "cantidad" no sirve comparar cuántas cayeron en
        // cada mitad: las dos mitades tienen la MISMA cantidad, porque el corte
        // se hace justo por la mitad de las extracciones. Lo que sí cambia —y es
        // lo que importa— es cada cuánto se extrae: veces por día.
        if (porCantidad) {
            var pa = porDia(prim), pb = porDia(seg);
            if (Math.abs(pb - pa) <= pa * 0.1) {
                return T('Te extraés unas {a} veces por día, parejo de punta a punta.', { a: dec(pa) });
            }
            if (pb > pa) {
                return T('Ahora te extraés más seguido: {b} veces por día, contra {a} al principio.',
                         { a: dec(pa), b: dec(pb) });
            }
            return T('Ahora te extraés menos seguido: {b} veces por día, contra {a} al principio.',
                     { a: dec(pa), b: dec(pb) });
        }

        function prom(lista) {
            return Math.round(lista.reduce(function (a, m) { return a + m.ml; }, 0) / lista.length);
        }
        var a = prom(prim), b = prom(seg);
        if (Math.abs(b - a) <= a * 0.05) {
            return T('Tu promedio se mantiene parejo: {a} al principio y {b} ahora.',
                     { a: fmtMl(a), b: fmtMl(b) });
        }
        if (b > a) {
            return T('Últimamente estás sacando más: {b} por extracción, contra {a} al principio.',
                     { a: fmtMl(a), b: fmtMl(b) });
        }
        return T('Últimamente estás sacando menos: {b} por extracción, contra {a} al principio.',
                 { a: fmtMl(a), b: fmtMl(b) });
    }

    // ── La tabla ─────────────────────────────────────────────────────────────
    function dibujarTabla(vx, grupos, muestras) {
        var filas = grupos.map(function (g) {
            return '<tr><th scope="row">' + esc(vx.etiqueta(g.clave)) + '</th>' +
                '<td>' + g.n + '</td>' +
                '<td>' + esc(fmtMl(g.suma)) + '</td>' +
                '<td>' + (g.n ? esc(fmtMl(g.promedio)) : '—') + '</td></tr>';
        }).join('');
        var total = muestras.reduce(function (a, m) { return a + (Number(m.ml) || 0); }, 0);
        var prom = muestras.length ? Math.round(total / muestras.length) : 0;

        return '<div class="lac-gr-tabla-scroll">' +
            '<table class="lac-gr-tabla">' +
            '<thead><tr>' +
                '<th scope="col">' + esc(vx.label()) + '</th>' +
                '<th scope="col">' + T('Extracciones') + '</th>' +
                '<th scope="col">' + T('Total') + '</th>' +
                '<th scope="col">' + T('Promedio') + '</th>' +
            '</tr></thead>' +
            '<tbody>' + filas + '</tbody>' +
            '<tfoot><tr><th scope="row">' + T('Todo') + '</th>' +
                '<td>' + muestras.length + '</td>' +
                '<td>' + esc(fmtMl(total)) + '</td>' +
                '<td>' + esc(fmtMl(prom)) + '</td></tr></tfoot>' +
            '</table></div>';
    }

    // ── Los desplegables ─────────────────────────────────────────────────────
    function opciones(lista, elegida, deshabilitarBebe) {
        return lista.map(function (v) {
            var off = deshabilitarBebe && v.requiereBebe;
            return '<option value="' + v.clave + '"' +
                (v.clave === elegida ? ' selected' : '') +
                (off ? ' disabled' : '') + '>' + esc(v.label()) + '</option>';
        }).join('');
    }

    function pintarSelects() {
        var sinBebe = !hayBebe();
        $('lac-gr-x').innerHTML = opciones(EJES_X, selX, sinBebe);
        $('lac-gr-y').innerHTML = opciones(EJES_Y, selY, false);
        var nota = $('lac-gr-nota-bebe');
        if (nota) nota.hidden = !sinBebe;
    }

    function recordar() {
        try {
            window.localStorage.setItem(MEMORIA, selX + '|' + selY);
        } catch (e) { /* modo privado: no se recuerda, y no pasa nada */ }
    }

    function recordado() {
        try {
            var v = String(window.localStorage.getItem(MEMORIA) || '').split('|');
            if (v.length === 2) {
                selX = buscarEje(EJES_X, v[0]).clave;
                selY = buscarEje(EJES_Y, v[1]).clave;
            }
        } catch (e) { /* ídem */ }
    }

    // ── Dibujar todo ─────────────────────────────────────────────────────────
    function vacio(emoji, titulo, sub) {
        return '<div class="lac-vacia">' +
            '<span class="lac-vacia-em">' + emoji + '</span>' +
            '<span class="lac-vacia-t">' + titulo + '</span>' +
            (sub ? '<span>' + sub + '</span>' : '') +
        '</div>';
    }

    function dibujar() {
        var lienzo = $('lac-gr-lienzo');
        var lect = $('lac-gr-lectura');
        var tabla = $('lac-gr-tabla');
        if (!lienzo) return;

        var todas = (DATOS && DATOS.muestras) || [];
        if (!todas.length) {
            lienzo.innerHTML = vacio('📈', T('Todavía no hay extracciones para graficar'),
                                     T('Cargá tus bolsitas y acá vas a poder cruzar tus datos.'));
            lect.innerHTML = '';
            tabla.innerHTML = '';
            return;
        }

        var vx = buscarEje(EJES_X, selX);
        var vy = buscarEje(EJES_Y, selY);

        // Las muestras que esta variable puede ubicar (una sin hora cargada no
        // entra en un gráfico por hora; una sin edad, en uno por día de vida).
        var muestras = todas.filter(function (m) {
            var g = vx.grupo(m);
            return g !== null && g !== undefined && !isNaN(g);
        });

        if (!muestras.length) {
            lienzo.innerHTML = vacio('🤔', T('Ninguna extracción tiene ese dato cargado'),
                                     T('Probá con otra variable en el eje horizontal.'));
            lect.innerHTML = '';
            tabla.innerHTML = '';
            return;
        }

        var grupos = agrupar(vx, muestras);
        var forma = tipoGrafico(vx, vy);

        lienzo.innerHTML = dibujarSvg(vx, vy, muestras, grupos, forma);
        lect.innerHTML = '<p class="lac-gr-lectura-txt">' + esc(lectura(vx, vy, muestras)) + '</p>' +
            '<p class="lac-gr-lectura-hint">' +
            T('Es lo que muestran tus datos, no una regla: cada mamá y cada día son únicos.') +
            '</p>';
        tabla.innerHTML = dibujarTabla(vx, grupos, muestras);
    }

    // ── Enganche con lactancia.js ────────────────────────────────────────────
    function init(ayudantes) {
        ayudantes = ayudantes || {};
        if (ayudantes.T) T = ayudantes.T;
        if (ayudantes.fmtMl) fmtMl = ayudantes.fmtMl;
        if (ayudantes.esc) esc = ayudantes.esc;
        if (ayudantes.fmtFechaCorta) fmtFechaCorta = ayudantes.fmtFechaCorta;
        recordado();
    }

    function render(datos) {
        DATOS = datos;
        if (!$('lac-gr-lienzo')) return;      // la pantalla no trae el bloque
        pintarSelects();
        if (!armado) {
            armado = true;
            ['lac-gr-x', 'lac-gr-y'].forEach(function (id) {
                $(id).addEventListener('change', function () {
                    selX = $('lac-gr-x').value;
                    selY = $('lac-gr-y').value;
                    recordar();
                    dibujar();
                });
            });
        }
        dibujar();
    }

    return { init: init, render: render };
})();
