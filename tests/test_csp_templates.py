# =============================================================================
# ARCHIVO: tests/test_csp_templates.py
# =============================================================================
#
# El front tiene que estar escrito para la POLÍTICA ESTRICTA DE SCRIPTS del
# servidor: Content-Security-Policy con `script-src 'self' 'nonce-<N>'`, SIN
# 'unsafe-inline' para scripts. Este test lo congela leyendo el código fuente.
#
# POR QUÉ ESTE TEST EXISTE
#   La política es la defensa de fondo contra el HTML inyectado: si alguna vez
#   se cuela un `<img src=x onerror=...>` por un dato mal escapado, el
#   navegador se niega a correr ese manejador. Pero se niega a correr TODO lo
#   inline que no traiga el nonce de la respuesta, también lo NUESTRO:
#     · un <script> inline sin `nonce="{{ csp_nonce }}"` no se ejecuta (la
#       página queda sin sus datos, sin su tema o sin sus botones);
#     · un `onclick="..."` no hace nada (el botón queda muerto);
#     · `javascript:`, `eval(` y `new Function(` también los corta.
#   Y falla EN SILENCIO: ningún test de Python corre JavaScript, así que sin
#   esto el error aparece recién en el navegador de Mari. La tentación en ese
#   momento es agregar 'unsafe-inline' a la política, que borra justo la
#   defensa que se quería. Acá el error se ve al correr los tests, en la línea
#   que lo causa.
#
# QUÉ CONGELA
#   1. Todo <script> inline de templates/*.html lleva nonce="{{ csp_nonce }}".
#      (Los <script src="..."> propios no lo necesitan: los cubre 'self'.)
#   2. Ninguna etiqueta de un template tiene atributos on<algo>= ni apunta a
#      una URL javascript:.
#   3. Ningún JS propio (static/**/*.js salvo vendor/, el service worker
#      templates/sw.js, ni el cuerpo de los <script> inline) arma HTML con
#      manejadores inline, ni usa javascript:, eval(, new Function(,
#      setAttribute('on...') o setTimeout/setInterval con un string en vez de
#      una función.
#   4. Cada data-accion que se usa en un template o en un string de JS tiene su
#      acción en el despachador delegado de app.js (ACCIONES). Sin esto, un
#      typo (`data-accion="borar"`) deja un botón muerto sin avisar a nadie.
#   5. Los detectores se prueban contra casos buenos y malos: una regex rota
#      dejaría pasar todo y los tests de arriba seguirían en verde para siempre.
#
# LÍMITES (honestos)
#   Es un escaneo ESTÁTICO y heurístico: no ejecuta JavaScript ni renderiza
#   Jinja. Los comentarios se ignoran con un tokenizador chico (cadenas,
#   plantillas, regex y comentarios) que, si se pierde, FALLA en voz alta en vez
#   de saltearse el archivo. Lo que no ve —un manejador armado con `+` partido
#   de forma rara, o un atributo que genera Jinja— lo ve el navegador: la
#   consola muestra "Refused to execute inline ..." cuando la política corta
#   algo. Ese chequeo manual sigue haciendo falta al tocar el front.
#
# CÓMO SUMAR UNA ACCIÓN NUEVA (data-accion): agregarla a la tabla ACCIONES de
#   static/app.js. Con `data-accion="algo"` en el HTML y sin la entrada en
#   ACCIONES, el test 4 falla.
#
# CÓMO CORRER:
#   python -m unittest tests.test_csp_templates -v
#
# =============================================================================

import glob
import os
import re
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(ROOT_DIR, 'static')
TEMPLATES_DIR = os.path.join(ROOT_DIR, 'templates')
APP_JS = os.path.join(STATIC_DIR, 'app.js')
SW_JS = os.path.join(TEMPLATES_DIR, 'sw.js')   # el service worker: NO es un template Jinja


def _leer(ruta):
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def _templates():
    rutas = sorted(glob.glob(os.path.join(TEMPLATES_DIR, '*.html')))
    assert rutas, f'no hay templates en {TEMPLATES_DIR}: ¿cambió la carpeta?'
    return rutas


def _javascripts_propios():
    """static/**/*.js salvo vendor/ (código de terceros: tiene su propia huella
    en tests/test_vendor_integridad.py y no se edita), más el service worker,
    que vive en templates/ pero es JavaScript propio (lo sirve la ruta /sw.js)."""
    rutas = []
    for carpeta, subcarpetas, archivos in os.walk(STATIC_DIR):
        subcarpetas[:] = [s for s in subcarpetas if s != 'vendor']
        rutas += [os.path.join(carpeta, a) for a in archivos if a.endswith('.js')]
    assert rutas, f'no hay JavaScript propio en {STATIC_DIR}: ¿cambió la carpeta?'
    if os.path.isfile(SW_JS):
        rutas.append(SW_JS)
    return sorted(rutas)


# =============================================================================
# TEMPLATES: comentarios y etiquetas
# =============================================================================
#
# Los comentarios de Jinja ({# ... #}) y de HTML (<!-- ... -->) no llegan al
# navegador como código: un `<script>` o un `onclick=` DENTRO de uno es solo
# texto (base.html y editar.html explican justamente eso en comentarios). Se
# reemplazan por sus saltos de línea para no correr los números de línea.

_COMENTARIO_JINJA = re.compile(r'\{#.*?#\}', re.DOTALL)
_COMENTARIO_HTML = re.compile(r'<!--.*?-->', re.DOTALL)


def _saltos(m):
    return '\n' * m.group(0).count('\n')


def sin_comentarios_de_template(html):
    """Primero los de Jinja: pueden contener `<!--` y se evalúan antes que HTML."""
    return _COMENTARIO_HTML.sub(_saltos, _COMENTARIO_JINJA.sub(_saltos, html))


# Los atributos de una etiqueta: cualquier carácter menos `>`, salvo dentro de
# comillas (un `>` en un valor, como el <svg> del favicon, no cierra la
# etiqueta). Las tres alternativas se excluyen entre sí por el primer carácter,
# así que no hay retroceso exponencial.
_ATRIBUTOS = r'''(?:[^>"']|"[^"]*"|'[^']*')*'''
_ETIQUETA_SCRIPT = re.compile(r'<script\b' + _ATRIBUTOS + '>', re.IGNORECASE)
_ETIQUETA_CUALQUIERA = re.compile(r'<[a-zA-Z][\w:-]*' + _ATRIBUTOS + '>')
_SCRIPT_Y_CUERPO = re.compile(
    r'(<script\b' + _ATRIBUTOS + r'>)(.*?)</script\s*>', re.IGNORECASE | re.DOTALL)

# nonce="{{ csp_nonce }}": se acepta con o sin espacios y con comillas dobles o
# simples, pero la variable tiene que ser exactamente `csp_nonce` (un nonce
# vacío o escrito a mano no sirve: cambia en cada respuesta).
_NONCE_OK = re.compile(
    r'''(?<![\w:-])nonce\s*=\s*["']\{\{\s*csp_nonce\s*\}\}["']''', re.IGNORECASE)
_ATRIBUTO_SRC = re.compile(r'(?<![\w:-])src\s*=', re.IGNORECASE)

# Un atributo on<algo>= (onclick, onerror, onload...). El `(?<![\w:.-])` evita
# `data-onclick=`, `x-on:click=` y `el.onclick =`. Se busca con los VALORES ya
# sacados, para no confundir un `title="onclick=foo"` con un manejador.
_MANEJADOR_EN_ETIQUETA = re.compile(r'(?<![\w:.-])on[a-z]+\s*=', re.IGNORECASE)

# Una URL javascript: en un atributo QUE ES una URL. Un `title="javascript: es
# un lenguaje"` es texto y no corre nada, así que no cuenta.
_URL_JAVASCRIPT_EN_ETIQUETA = re.compile(
    r'''(?<![\w:-])(?:href|src|action|formaction|data|poster|xlink:href)'''
    r'''\s*=\s*["']?\s*javascript\s*:''', re.IGNORECASE)


def _sin_valores(etiqueta):
    """La etiqueta con el contenido de las comillas vaciado."""
    return re.sub(r'''"[^"]*"|'[^']*\'''', '""', etiqueta)


def scripts_inline_sin_nonce(html):
    """Los <script> inline (sin src) que NO llevan nonce="{{ csp_nonce }}"."""
    html = sin_comentarios_de_template(html)
    return [e for e in _ETIQUETA_SCRIPT.findall(html)
            if not _ATRIBUTO_SRC.search(_sin_valores(e)) and not _NONCE_OK.search(e)]


def cuerpos_de_scripts_inline(html):
    """El JavaScript de cada <script> inline (sin src) de un template."""
    html = sin_comentarios_de_template(html)
    return [cuerpo for etiqueta, cuerpo in _SCRIPT_Y_CUERPO.findall(html)
            if not _ATRIBUTO_SRC.search(_sin_valores(etiqueta))]


def _html_sin_cuerpo_de_scripts(html):
    """El template sin comentarios y sin el JavaScript de los <script>: lo que
    queda son las etiquetas HTML (el JS tiene su propio chequeo, más abajo)."""
    return _SCRIPT_Y_CUERPO.sub(r'\1</script>', sin_comentarios_de_template(html))


def etiquetas_con_manejador_inline(html):
    """Etiquetas HTML con un atributo on<algo>=. Lista vacía = limpio."""
    return [e for e in _ETIQUETA_CUALQUIERA.findall(_html_sin_cuerpo_de_scripts(html))
            if _MANEJADOR_EN_ETIQUETA.search(_sin_valores(e))]


def etiquetas_con_url_javascript(html):
    """Etiquetas HTML con un atributo cuyo valor es una URL javascript:."""
    return [e for e in _ETIQUETA_CUALQUIERA.findall(_html_sin_cuerpo_de_scripts(html))
            if _URL_JAVASCRIPT_EN_ETIQUETA.search(e)]


# =============================================================================
# JAVASCRIPT: sacar los comentarios sin tocar las cadenas
# =============================================================================
#
# Los comentarios del repo explican los ataques con ejemplos reales
# (`<img src=x onerror=...>` en app.js, resumen.js y rutina.js), así que los
# detectores tienen que ignorarlos. Y las CADENAS no se pueden tocar: ahí es
# justamente donde vive el HTML con `onclick="..."`. Para distinguirlos hace
# falta un tokenizador mínimo: una regex tonta confunde el `//` de
# 'http://...' con un comentario y el `"` de /"/g con el inicio de una cadena.
#
# Cubre comentarios `//` y `/* */`, cadenas '...' y "...", plantillas `...`
# (con ${ } y plantillas anidadas) y regex literales. Un `/` es regex o
# división según el token anterior (la heurística clásica). Si se pierde
# (cadena o regex sin cerrar) lanza CodigoNoAnalizable: un escaneo que se
# saltea un archivo en silencio es peor que no tener escaneo.

class CodigoNoAnalizable(Exception):
    """El tokenizador de JS se perdió. Suele ser un `/` que tomó por regex."""


# Tras estos signos y palabras, un `/` abre una regex; tras cualquier otra
# cosa (identificador, número, `)`, `]`, cadena) es una división.
_ANTES_DE_REGEX = set('(,=:[!&|?{};+-*%<>~^}')
_PALABRAS_ANTES_DE_REGEX = {
    'return', 'typeof', 'case', 'in', 'of', 'else', 'do', 'void', 'delete',
    'new', 'throw', 'yield', 'await', 'instanceof',
}

# Una racha de caracteres "aburridos" (identificadores, espacios, signos que
# no abren nada): atajo para no recorrer 600 KB de JS letra por letra.
_RACHA = re.compile(r'''[\w$]+|\s+|[^\w$\s/'"`{}]+''')


def sin_comentarios_js(codigo, conservar_literales=True):
    """El JS sin comentarios. Las cadenas, plantillas y regex quedan intactas
    (`conservar_literales=True`) o con el contenido en blanco (False, para
    analizar solo la estructura: llaves, claves). Conserva todos los saltos de
    línea, así los números de línea siguen siendo los del archivo original."""
    n = len(codigo)
    salida = []
    i = 0
    ultimo = ''    # último token significativo: una palabra o un signo suelto
    pila = []      # un contador por cada "${" abierto: cuántas "{" propias lleva

    def linea(pos):
        return codigo.count('\n', 0, pos) + 1

    def literal(texto):
        return texto if conservar_literales else re.sub(r'[^\n]', ' ', texto)

    while i < n:
        m = _RACHA.match(codigo, i)
        if m:
            texto = m.group(0)
            salida.append(texto)
            if not texto.isspace():
                ultimo = texto if (texto[0].isalnum() or texto[0] in '_$') else texto[-1]
            i = m.end()
            continue

        c = codigo[i]
        sig = codigo[i + 1] if i + 1 < n else ''

        if c == '/' and sig == '/':                        # comentario de línea
            fin = codigo.find('\n', i)
            i = n if fin == -1 else fin
            continue

        if c == '/' and sig == '*':                        # comentario de bloque
            fin = codigo.find('*/', i + 2)
            if fin == -1:
                raise CodigoNoAnalizable(f'comentario sin cerrar (línea {linea(i)})')
            salida.append(' ' + '\n' * codigo.count('\n', i, fin))
            i = fin + 2
            continue

        if c in '\'"':                                     # cadena
            j = i + 1
            while j < n and codigo[j] != c:
                if codigo[j] == '\\':
                    j += 1
                elif codigo[j] == '\n':
                    raise CodigoNoAnalizable(f'cadena sin cerrar (línea {linea(i)})')
                j += 1
            if j >= n:
                raise CodigoNoAnalizable(f'cadena sin cerrar (línea {linea(i)})')
            salida.append(literal(codigo[i:j + 1]))
            i = j + 1
            ultimo = '"'
            continue

        if c == '`' or (c == '}' and pila and pila[-1] == 0):   # plantilla
            # Se entra desde la "`" que la abre, o desde la "}" que cierra un
            # "${ ... }" y devuelve el control al texto de la plantilla.
            if c == '}':
                pila.pop()
            j = i + 1
            abre_expresion = False
            while j < n:
                if codigo[j] == '\\':
                    j += 2
                    continue
                if codigo[j] == '`':
                    j += 1
                    break
                if codigo[j] == '$' and codigo[j + 1:j + 2] == '{':
                    pila.append(0)
                    abre_expresion = True
                    j += 2
                    break
                j += 1
            else:
                raise CodigoNoAnalizable(f'plantilla sin cerrar (línea {linea(i)})')
            salida.append(literal(codigo[i:j]))
            i = j
            ultimo = '(' if abre_expresion else '"'
            continue

        if c == '/' and (ultimo == '' or ultimo in _ANTES_DE_REGEX
                         or ultimo in _PALABRAS_ANTES_DE_REGEX):    # regex
            j = i + 1
            en_clase = False
            while j < n:
                d = codigo[j]
                if d == '\\':
                    j += 2
                    continue
                if d == '\n':
                    raise CodigoNoAnalizable(f'regex sin cerrar (línea {linea(i)})')
                if en_clase:
                    if d == ']':
                        en_clase = False
                elif d == '[':
                    en_clase = True
                elif d == '/':
                    break
                j += 1
            else:
                raise CodigoNoAnalizable(f'regex sin cerrar (línea {linea(i)})')
            j += 1
            while j < n and codigo[j].isalpha():          # banderas: g, i, m...
                j += 1
            salida.append(literal(codigo[i:j]))
            i = j
            ultimo = '"'
            continue

        # Lo que queda: una "/" de división y las llaves.
        if c == '{' and pila:
            pila[-1] += 1
        elif c == '}' and pila:
            pila[-1] -= 1
        salida.append(c)
        ultimo = c
        i += 1

    if pila:
        raise CodigoNoAnalizable('una plantilla "${" quedó sin cerrar')
    return ''.join(salida)


# =============================================================================
# JAVASCRIPT: lo que la política bloquea
# =============================================================================

# (nombre de la regla, regex). Se aplican al JS SIN comentarios y CON cadenas.
_REGLAS_JS = (
    # `onclick="..."` dentro de un string que arma HTML. Pegado al `=` y con
    # comilla enseguida: así no salta con `var online = "si"` ni con un
    # `?once=1` de una URL. `\\?` cubre la comilla escapada de un string.
    ('manejador inline armado como HTML (on<algo>="...")',
     re.compile(r'''(?<![\w.$:-])on[a-z]+=\\?["']''', re.IGNORECASE)),
    ("setAttribute('on<algo>', ...)",
     re.compile(r'''\bsetAttribute\(\s*["']on[a-z]+["']''', re.IGNORECASE)),
    # Una cadena que EMPIEZA con javascript: (href, location...). Un texto
    # como 'Activá JavaScript: ...' no empieza así y no cuenta.
    ('URL javascript:',
     re.compile(r'''["'`]\s*javascript\s*:''', re.IGNORECASE)),
    ('eval()',
     re.compile(r'(?<![\w$])eval\s*\(')),
    ('new Function() / Function()',
     re.compile(r'\bnew\s+Function\b|(?<![\w$.])Function\s*\(')),
    ('setTimeout/setInterval con un string en vez de una función',
     re.compile(r'''\bset(?:Timeout|Interval)\s*\(\s*["'`]''')),
)


def problemas_js(codigo):
    """Lo que la política de scripts bloquearía en este JS, como una lista de
    (regla, línea, extracto). Lista vacía = limpio. Puede lanzar
    CodigoNoAnalizable."""
    limpio = sin_comentarios_js(codigo)
    halladas = []
    for regla, patron in _REGLAS_JS:
        for m in patron.finditer(limpio):
            linea = limpio.count('\n', 0, m.start()) + 1
            extracto = limpio[m.start():m.start() + 70].split('\n')[0]
            halladas.append((regla, linea, extracto))
    return halladas


# =============================================================================
# data-accion: el despachador delegado de app.js
# =============================================================================

# Valor de un atributo data-accion en HTML ("..." o '...') o en un string de JS
# (con la comilla escapada: data-accion=\"borrar\").
_DATA_ACCION = re.compile(r'''data-accion\s*=\s*\\?["']([^"'\\\s>]*)''')


def acciones_definidas(codigo_app_js):
    """Las claves de la tabla ACCIONES de app.js (el despachador de data-accion),
    o None si no se encuentra la tabla."""
    limpio = sin_comentarios_js(codigo_app_js, conservar_literales=False)
    m = re.search(r'\bACCIONES\s*=\s*\{', limpio)
    if m is None:
        return None
    profundidad = 1
    primer_nivel = []
    for c in limpio[m.end():]:
        if c == '{':
            profundidad += 1
        elif c == '}':
            profundidad -= 1
            if profundidad == 0:
                break
        primer_nivel.append(c if profundidad == 1 else ' ')
    return set(re.findall(r'([\w$]+)\s*:', ''.join(primer_nivel)))


def acciones_usadas():
    """{valor de data-accion: [archivos donde se usa]} en templates y JS propio."""
    usadas = {}

    def anotar(texto, donde):
        for valor in _DATA_ACCION.findall(texto):
            usadas.setdefault(valor, []).append(donde)

    for ruta in _templates():
        html = _leer(ruta)
        nombre = os.path.basename(ruta)
        anotar(_html_sin_cuerpo_de_scripts(html), nombre)
        for cuerpo in cuerpos_de_scripts_inline(html):
            anotar(sin_comentarios_js(cuerpo), nombre)
    for ruta in _javascripts_propios():
        anotar(sin_comentarios_js(_leer(ruta)), os.path.basename(ruta))
    return usadas


# =============================================================================
# LOS TESTS
# =============================================================================

class TestScriptsInlineConNonce(unittest.TestCase):

    def test_todo_script_inline_lleva_nonce(self):
        """
        EL test de la mitad HTML. Un <script> inline sin nonce lo bloquea el
        navegador: la página queda sin los datos que el servidor inyecta
        (GASTOS_FIJOS, RUT_DATOS...) o sin el tema del anti-flicker. Si falla:
        el tag tiene que ser `<script nonce="{{ csp_nonce }}">`. Si el script
        es grande, mejor moverlo a static/*.js y cargarlo con <script src>.
        """
        for ruta in _templates():
            with self.subTest(template=os.path.basename(ruta)):
                self.assertEqual(
                    scripts_inline_sin_nonce(_leer(ruta)), [],
                    f'{os.path.basename(ruta)} tiene un <script> inline sin '
                    f'nonce="{{{{ csp_nonce }}}}": la política de scripts del '
                    f'servidor lo bloquea.')

    def test_el_regex_ve_todas_las_etiquetas_script(self):
        """Si una etiqueta <script> no se pudiera parsear (comillas sin
        cerrar, por ejemplo), el test de arriba pasaría sin haberla mirado.
        Acá se cruza la cuenta de `<script` del texto con las etiquetas
        que el regex logra leer."""
        for ruta in _templates():
            with self.subTest(template=os.path.basename(ruta)):
                html = sin_comentarios_de_template(_leer(ruta))
                self.assertEqual(
                    len(re.findall(r'<script\b', html, re.IGNORECASE)),
                    len(_ETIQUETA_SCRIPT.findall(html)),
                    f'{os.path.basename(ruta)}: hay un <script> que el detector '
                    f'no pudo leer entero (¿comillas sin cerrar en la etiqueta?).')

    def test_el_escaneo_no_es_vacio(self):
        """Las páginas siguen trayendo sus scripts inline: si el conteo diera
        cero, el regex estaría roto y los tests de arriba, en verde por
        vacío."""
        con_nonce = 0
        for ruta in _templates():
            html = sin_comentarios_de_template(_leer(ruta))
            con_nonce += sum(1 for e in _ETIQUETA_SCRIPT.findall(html)
                             if _NONCE_OK.search(e))
        self.assertGreater(con_nonce, 0, 'ningún template tiene un <script> con '
                                         'nonce: ¿se rompió el detector?')


class TestTemplatesSinManejadoresInline(unittest.TestCase):

    def test_ninguna_etiqueta_tiene_atributos_on(self):
        """
        Un `onclick="..."` en el HTML no corre bajo la política: el botón queda
        muerto sin ningún error visible. El evento se engancha con
        addEventListener (o, para borrar y navegar, con data-accion: ver
        ACCIONES en static/app.js).
        """
        for ruta in _templates():
            with self.subTest(template=os.path.basename(ruta)):
                self.assertEqual(
                    etiquetas_con_manejador_inline(_leer(ruta)), [],
                    f'{os.path.basename(ruta)} tiene un manejador inline '
                    f'(on<algo>=...): la política de scripts lo bloquea. Usar '
                    f'data-accion o addEventListener.')

    def test_ninguna_etiqueta_apunta_a_una_url_javascript(self):
        for ruta in _templates():
            with self.subTest(template=os.path.basename(ruta)):
                self.assertEqual(
                    etiquetas_con_url_javascript(_leer(ruta)), [],
                    f'{os.path.basename(ruta)} tiene una URL javascript:, que '
                    f'la política de scripts bloquea.')


class TestJavaScriptCompatibleConLaPolitica(unittest.TestCase):

    def _revisar(self, nombre, codigo):
        try:
            problemas = problemas_js(codigo)
        except CodigoNoAnalizable as e:
            self.fail(f'{nombre}: el analizador se perdió ({e}). Si el código es '
                      f'válido, hay que ajustar sin_comentarios_js() de este test: '
                      f'un archivo sin escanear no se puede dar por limpio.')
        self.assertEqual(
            problemas, [],
            f'{nombre} usa algo que la política de scripts bloquea: '
            + '; '.join(f'línea {linea}: {regla}: {extracto!r}'
                        for regla, linea, extracto in problemas))

    def test_los_js_propios_no_usan_nada_que_la_politica_bloquee(self):
        """
        Antes `crearFilaMovimiento` (app.js) armaba el ✕ de cada fila con un
        `onclick="mostrarModalBorrado(...)"` dentro del innerHTML: bajo la
        política el botón dejaría de responder. Hoy lleva data-accion="borrar".
        """
        for ruta in _javascripts_propios():
            with self.subTest(archivo=os.path.basename(ruta)):
                self._revisar(os.path.basename(ruta), _leer(ruta))

    def test_los_scripts_inline_de_los_templates_tampoco(self):
        """El JS de un <script nonce=...> corre, pero sigue bajo la misma
        política: el eval, el `javascript:` y el HTML con onclick= también lo
        cortan ahí."""
        for ruta in _templates():
            for numero, cuerpo in enumerate(cuerpos_de_scripts_inline(_leer(ruta)), 1):
                nombre = f'{os.path.basename(ruta)} (script inline #{numero})'
                with self.subTest(script=nombre):
                    self._revisar(nombre, cuerpo)

    def test_se_escanea_algo(self):
        """Anti-vacío: si el recorrido de carpetas o el regex de <script>
        se rompieran, los dos tests de arriba pasarían sin haber mirado nada."""
        nombres = {os.path.basename(r) for r in _javascripts_propios()}
        self.assertTrue({'app.js', 'rutina.js', 'lactancia.js'} <= nombres, nombres)
        cuerpos = [c for r in _templates() for c in cuerpos_de_scripts_inline(_leer(r))]
        self.assertGreater(len(cuerpos), 0, 'ningún template tiene un <script> inline')


class TestDespachadorDataAccion(unittest.TestCase):

    def test_app_js_define_borrar_y_navegar(self):
        definidas = acciones_definidas(_leer(APP_JS))
        self.assertIsNotNone(definidas, 'no encuentro la tabla ACCIONES en app.js')
        self.assertTrue({'borrar', 'navegar'} <= definidas, definidas)

    def test_cada_data_accion_usado_tiene_su_accion(self):
        """
        Un `data-accion="borar"` (typo) o una acción que alguien usó sin
        escribir su entrada en ACCIONES deja un botón muerto, con el mismo
        síntoma que un manejador inline bloqueado. Acá el desfasaje se ve.
        """
        definidas = acciones_definidas(_leer(APP_JS))
        self.assertIsNotNone(definidas, 'no encuentro la tabla ACCIONES en app.js')
        usadas = acciones_usadas()
        self.assertTrue(usadas, 'ningún template usa data-accion: ¿se rompió el '
                                'detector, o se volvió a onclick?')
        for valor, donde in sorted(usadas.items()):
            with self.subTest(accion=valor):
                self.assertIn(
                    valor, definidas,
                    f'data-accion="{valor}" (en {", ".join(sorted(set(donde)))}) '
                    f'no existe en ACCIONES de static/app.js: el botón no haría nada.')


class TestDetectores(unittest.TestCase):
    """Sin esto, una regex rota dejaría pasar el onclick, el <script> sin nonce
    o el eval(, y los tests de arriba seguirían en verde para siempre."""

    def test_scripts_inline_sin_nonce(self):
        malos = [
            '<script>var a = 1;</script>',
            '<script type="text/javascript">x()</script>',
            '<SCRIPT>x()</SCRIPT>',
            '<script nonce="">x()</script>',                       # nonce vacío
            '<script nonce="abc123">x()</script>',                 # escrito a mano
            '<script nonce="{{ otra_variable }}">x()</script>',    # variable equivocada
            '<script\n   defer>x()</script>',
            '<script data-src="x.js" async>x()</script>',          # data-src NO es src
            '<script>if (a > b) { x() }</script>',                 # `>` en el cuerpo
            '<script title="a > b">x()</script>',                  # `>` en un valor
            '<script type="module">import("x")</script>',
        ]
        for html in malos:
            with self.subTest(html=html):
                self.assertTrue(scripts_inline_sin_nonce(html), 'el detector no lo vio')

        buenos = [
            '<script nonce="{{ csp_nonce }}">x()</script>',
            '<script nonce="{{csp_nonce}}">x()</script>',
            "<script nonce='{{ csp_nonce }}'>x()</script>",
            '<script type="module" nonce="{{ csp_nonce }}">x()</script>',
            '<script nonce="{{ csp_nonce }}" title="a > b">x()</script>',
            '<script src="/static/app.js"></script>',              # propio: lo cubre 'self'
            "<script src=\"{{ url_for('static', filename='app.js') }}?v={{ static_version }}\"></script>",
            '<script defer src="/static/app.js"></script>',
            '{# <script>x()</script> #}',                          # comentario de Jinja
            '<!-- <script>x()</script> -->',                       # comentario de HTML
            '<p>este script <b>no</b> es una etiqueta</p>',
        ]
        for html in buenos:
            with self.subTest(html=html):
                self.assertEqual(scripts_inline_sin_nonce(html), [])

    def test_cuerpos_de_scripts_inline(self):
        html = ('<script src="a.js"></script>'
                '<script nonce="{{ csp_nonce }}">var a = 1;</script>'
                '{# <script>comentado()</script> #}'
                '<script>var b = 2;</script>')
        self.assertEqual(cuerpos_de_scripts_inline(html), ['var a = 1;', 'var b = 2;'])

    def test_manejadores_inline_en_etiquetas(self):
        malos = [
            '<button onclick="x()">',
            "<button type=\"button\" onclick='x()'>",
            '<a href="#" ONCLICK="x()">',
            '<img src=x onerror=alert(1)>',
            '<img/src=x/onerror=alert(1)>',
            '<body onload="init()">',
            '<input value="a>b" onfocus="x()">',                   # `>` en un valor
            '<form\n  onsubmit="return f()">',
            '<svg onload="x()"></svg>',
            "<div {{ 'x' }} onmouseover=\"a()\">",
            '<script onerror="x()" src="a.js"></script>',
            '<button class="btn" onclick = "x()">',
        ]
        for html in malos:
            with self.subTest(html=html):
                self.assertTrue(etiquetas_con_manejador_inline(html), 'el detector no lo vio')

        buenos = [
            '<button type="button" data-accion="borrar">',
            '<button data-onclick="x">',
            '<a title="onclick=foo" href="#">',                    # dentro de un valor
            '<input class="online" value="once=1">',
            '<button id="btn-crear-backup">',
            '<script>var a = { onclick: 1 }; el.onclick = f; var online = 1;</script>',
            '<script nonce="{{ csp_nonce }}">el.innerHTML = \'<b onclick="x()">\';</script>',  # eso lo ve el chequeo de JS
            '<p>escribí onclick="algo" en el HTML</p>',            # texto, no etiqueta
            '{# <button onclick="x()"> #}',
            '<!-- <b onclick="x()"> -->',
            '<x-on:click>',
        ]
        for html in buenos:
            with self.subTest(html=html):
                self.assertEqual(etiquetas_con_manejador_inline(html), [])

    def test_urls_javascript_en_etiquetas(self):
        for html in ('<a href="javascript:void(0)">', "<a href='JavaScript:x()'>",
                     '<form action=" javascript:x()">', '<iframe src=javascript:x()>'):
            with self.subTest(html=html):
                self.assertTrue(etiquetas_con_url_javascript(html), 'el detector no lo vio')
        for html in ('<a href="/gastos">', '<a title="javascript: es un lenguaje">',
                     '<p>javascript:void(0)</p>', '<!-- <a href="javascript:x()"> -->'):
            with self.subTest(html=html):
                self.assertEqual(etiquetas_con_url_javascript(html), [])

    def test_problemas_en_js(self):
        malos = [
            "el.innerHTML = '<button onclick=\"borrar()\">x</button>';",
            "html += \"<a href='#' onclick='x()'>\";",
            "'<img src=x onerror=\"x()\">'",
            "'<button type=\\\"button\\\" onclick=\\\"x()\\\">'",    # comillas escapadas
            "fila.innerHTML = '<td ' + 'onclick=\"x()\"' + '>';",   # partido con +
            "el.innerHTML = `<b onclick=\"x()\">${a}</b>`;",         # plantilla
            "el.setAttribute('onclick', 'x()');",
            'el.setAttribute("onmouseover", "x()");',
            "a.href = 'javascript:void(0)';",
            "'<a href=\"javascript:x()\">'",
            "eval('1+1');",
            'window.eval(codigo);',
            "new Function('a', 'return a');",
            "Function('return 1')();",
            'setTimeout("x()", 100);',
            "setInterval('x()', 100);",
            'setTimeout(`x()`, 1);',
        ]
        for js in malos:
            with self.subTest(js=js):
                self.assertTrue(problemas_js(js), 'el detector no lo vio')

        buenos = [
            "btn.addEventListener('click', f);",
            'el.onclick = function () {};',                         # propiedad con una función
            "var online = true; var once = 'a'; var onlyFilled = \"x\";",
            "el.innerHTML = '<button data-accion=\"borrar\">x</button>';",
            '// <img src=x onerror=...> ejemplo de ataque, en un comentario',
            'x = 1; // y javascript: eval( new Function( onclick="a"',
            '/* onclick="x()" + javascript:void(0) + eval(x) */ var a = 1;',
            "var u = 'http://example.com/a?once=1&only=2';",         # `//` y `once=` en una cadena
            "setTimeout(function () {}, 10); setTimeout(f, 10); setInterval(g, 5);",
            'retrieval(1); medieval (2); obj.evaluar(3);',
            "var t = 'Activá JavaScript: así anda';",                # texto que NO empieza con javascript:
            "s.replace(/<script>/g, '');",
            "s.replace(/\"/g, '&quot;').replace(/'/g, '&#39;');",     # regex con comillas
            "var d = a / b; var e = c / d; // división",
            "html = a ? '<b>' : '</b>';",
            'var t = `x ${a ? `y ${b}` : \'z\'} w`;',                # plantilla anidada
            'data.map(b => `<option value="${b.id}">${b.nombre}</option>`);',
        ]
        for js in buenos:
            with self.subTest(js=js):
                self.assertEqual(problemas_js(js), [])

    def test_el_tokenizador_saca_comentarios_y_respeta_las_cadenas(self):
        casos = [
            ("var u = 'http://x.com'; // c", "var u = 'http://x.com'; "),
            ('a = 1; /* uno\ndos */ b = 2;', 'a = 1;  \n b = 2;'),
            ("s.replace(/\"/g, 'x') // c", "s.replace(/\"/g, 'x') "),
            ("/[/]/.test(x) // c", "/[/]/.test(x) "),
            ('a / b // c', 'a / b '),
            ('x = "a // b" + \'c /* d */\'; // e', 'x = "a // b" + \'c /* d */\'; '),
            ('t = `a ${ {b: \'}\'}.b } c`; // d', 't = `a ${ {b: \'}\'}.b } c`; '),
            ('return /x"/.test(s); // c', 'return /x"/.test(s); '),
        ]
        for entrada, esperada in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(sin_comentarios_js(entrada), esperada)

    def test_el_tokenizador_conserva_los_saltos_de_linea(self):
        codigo = 'a;\n/* x\ny\nz */\nb; // c\nd;\n'
        self.assertEqual(sin_comentarios_js(codigo).count('\n'), codigo.count('\n'))

    def test_el_tokenizador_puede_ocultar_las_cadenas(self):
        """Con conservar_literales=False las cadenas quedan en blanco (mismo
        largo): así se cuentan las llaves de la estructura sin que una '}'
        dentro de un string las desbalancee."""
        oculto = sin_comentarios_js("o = { k: 'a}b' }; // c", conservar_literales=False)
        self.assertEqual(oculto, 'o = { k: ' + ' ' * len("'a}b'") + ' }; ')
        self.assertEqual(oculto.count('{'), oculto.count('}'))

    def test_el_tokenizador_falla_en_voz_alta_si_se_pierde(self):
        for roto in ("var a = 'sin cerrar;\nvar b = 1;", 'var a = "sin cerrar',
                     'var a = `sin cerrar', '/* sin cerrar', 'x = /sin cerrar\ny;'):
            with self.subTest(js=roto):
                with self.assertRaises(CodigoNoAnalizable):
                    sin_comentarios_js(roto)

    def test_el_regex_de_data_accion(self):
        encontrados = [
            ('<button data-accion="borrar">', ['borrar']),
            ("<button data-accion='navegar' data-url=\"/gastos\">", ['navegar']),
            ('<button data-accion = "borrar">', ['borrar']),
            ("'<button data-accion=\\\"borrar\\\">✕</button>'", ['borrar']),   # comillas escapadas en JS
            ('<b data-accion="a"></b><i data-accion="b"></i>', ['a', 'b']),
            ('<button data-accion="borar">', ['borar']),                       # el typo SÍ se lee: lo ataja el test del despachador
        ]
        for texto, esperado in encontrados:
            with self.subTest(texto=texto):
                self.assertEqual(_DATA_ACCION.findall(texto), esperado)
        for texto in ('<b data-acciones="x">', '<b data-accion-x="y">',
                      '<b data-url="/gastos">', '<b accion="borrar">'):
            with self.subTest(texto=texto):
                self.assertEqual(_DATA_ACCION.findall(texto), [])

    def test_acciones_definidas(self):
        js = '''
        // var ACCIONES = { falsa: 1 };   (comentario: no cuenta)
        (function () {
            var ACCIONES = {
                borrar: function (o) { var x = { interno: 1 }; f(o); },
                navegar: function (o) { if (a) { g(); } },
                'otra-cosa': function () {}
            };
            document.addEventListener('click', function () { ACCIONES.borrar(); });
        })();
        '''
        # `interno` está a otra profundidad y `'otra-cosa'` es una cadena (su
        # clave entre comillas no se lee: las acciones se nombran con palabras).
        self.assertEqual(acciones_definidas(js), {'borrar', 'navegar'})
        self.assertIsNone(acciones_definidas('var otra = { a: 1 };'))


if __name__ == '__main__':
    unittest.main()
