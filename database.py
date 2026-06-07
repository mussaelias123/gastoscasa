# =============================================================================
# ARCHIVO: database.py
# =============================================================================
#
# QUÉ ES ESTE ARCHIVO:
#   Este módulo se encarga de TODA la comunicación con la base de datos.
#   Contiene las funciones que ejecutan queries SQL: SELECT, INSERT, DELETE
#   y el cálculo dinámico de saldos.
#
# ROL EN EL PROYECTO:
#   Backend → Capa de datos (Data Layer)
#   Este archivo NO sabe nada del navegador, ni de las URLs, ni de HTML.
#   Solo sabe hablar con la base de datos. Eso es buena práctica: separar
#   responsabilidades. (En inglés: "Separation of Concerns")
#
# ANALOGÍA CON PLCs:
#   Es como un bloque de función (FB) dedicado a leer/escribir en la
#   memoria remanente o en una receta (recipe). El bloque no sabe quién
#   lo llama ni para qué: solo hace su trabajo de almacenar y recuperar datos.
#
# BASE DE DATOS UTILIZADA: SQLite
#   - SQLite es SQL estándar (como el que ya conocés), pero guardado en un
#     ARCHIVO LOCAL (.db) en lugar de en un servidor separado.
#   - No requiere instalar nada extra: viene incluido con Python.
#   - El archivo gastos.db se crea automáticamente la primera vez que
#     corrés la aplicación.
#
# MODELO DE DATOS:
#   Hay UNA tabla: movimientos.
#   Cada fila es un movimiento de dinero: ingreso o gasto, de una persona,
#   en una moneda. Los SALDOS no se guardan: se calculan sumando/restando
#   todos los movimientos en cada consulta. Esto garantiza que los saldos
#   siempre sean consistentes con el historial.
#
# =============================================================================

import sqlite3    # Librería estándar de Python para SQLite (ya viene incluida)
import os         # Para trabajar con rutas de archivos
import re         # Para validar el formato de fecha en calcular_saldos(hasta)


# =============================================================================
# CONFIGURACIÓN: Ruta del archivo de base de datos
# =============================================================================
#
# __file__ es una variable especial de Python que contiene la ruta de este
# archivo (database.py). Usamos eso para construir la ruta absoluta al
# archivo .db, de forma que funcione sin importar desde qué carpeta se ejecute.
#
DB_PATH = os.path.join(os.path.dirname(__file__), 'gastos.db')


# =============================================================================
# FUNCIÓN: conectar()
# Propósito: Abre (o crea) la conexión con el archivo de base de datos.
# =============================================================================
#
# Cada vez que necesitamos hablar con la BD, abrimos una conexión,
# hacemos lo que necesitamos, y la cerramos. Es como abrir y cerrar
# un archivo de texto: no lo dejás abierto todo el tiempo.
#
def conectar():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)

    # row_factory = sqlite3.Row hace que cada fila devuelta sea como un
    # diccionario: podés acceder a las columnas por nombre en vez de por índice.
    # En vez de fila[2], podés escribir fila['descripcion']. Más legible.
    conn.row_factory = sqlite3.Row

    return conn


# =============================================================================
# FUNCIÓN: inicializar_db()
# Propósito: Crea la tabla si no existe. Se llama una sola vez al iniciar.
# =============================================================================
#
# ESTRUCTURA DE LA TABLA movimientos:
#   id          → clave primaria autoincremental (identificador único)
#   fecha       → texto con formato 'YYYY-MM-DD'
#   descripcion → descripción libre del movimiento
#   persona     → quién hizo el movimiento: 'elias' o 'mari'
#   moneda      → en qué moneda: 'ars' (pesos) o 'usd' (dólares)
#   tipo        → 'ingreso' (suma al saldo) o 'gasto' (resta al saldo)
#   monto       → valor numérico, siempre positivo
#
def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimientos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT    NOT NULL,
            descripcion     TEXT    NOT NULL,
            persona         TEXT    NOT NULL,
            moneda          TEXT    NOT NULL,
            tipo            TEXT    NOT NULL,
            monto           REAL    NOT NULL,
            factor_aplicado REAL    DEFAULT NULL
        )
    ''')

    # Agregar columnas nuevas si no existen (para bases de datos ya existentes)
    # monto_usd: equivalente del movimiento en dólares, guardado al insertar/editar.
    # cotizacion_usd_aplicada: cotización ARS→USD usada al calcular monto_usd.
    #                          NULL para movimientos en USD (no hay conversión).
    for columna, definicion in [
        ('categoria', 'TEXT'), ('costo_envio', 'REAL'), ('factor_aplicado', 'REAL'),
        ('cuota_numero', 'INTEGER'), ('cuota_total', 'INTEGER'),
        ('monto_usd', 'REAL'), ('cotizacion_usd_aplicada', 'REAL'),
    ]:
        try:
            cursor.execute(f'ALTER TABLE movimientos ADD COLUMN {columna} {definicion}')
        except Exception:
            pass  # La columna ya existe, ignorar el error

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_fijos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion TEXT    NOT NULL,
            activo      INTEGER NOT NULL DEFAULT 1
        )
    ''')

    # Migración: si la tabla tiene el esquema viejo (con columna 'persona'), recrearla
    cols = [row[1] for row in cursor.execute('PRAGMA table_info(gastos_fijos)').fetchall()]
    if 'persona' in cols:
        cursor.execute('DROP TABLE gastos_fijos')
        cursor.execute('''
            CREATE TABLE gastos_fijos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                descripcion TEXT    NOT NULL,
                activo      INTEGER NOT NULL DEFAULT 1
            )
        ''')

    # Agregar columnas de cuotas a gastos_fijos si no existen
    for columna, definicion in [
        ('es_cuota', 'INTEGER DEFAULT 0'),
        ('total_cuotas', 'INTEGER'),
        ('cuota_actual', 'INTEGER DEFAULT 0'),
    ]:
        try:
            cursor.execute(f'ALTER TABLE gastos_fijos ADD COLUMN {columna} {definicion}')
        except Exception:
            pass  # La columna ya existe, ignorar el error

    conn.commit()   # Confirma los cambios (como un "guardar")
    conn.close()    # Cierra la conexión


# =============================================================================
# FUNCIÓN: calcular_saldos()
# Propósito: Calcula los 4 saldos dinámicamente desde los movimientos.
# =============================================================================
#
# Los saldos NO están guardados en la BD. Se calculan siempre sumando los
# ingresos y restando los gastos de cada combinación persona/moneda.
#
# SQL equivalente (simplificado para elias/ars):
#   SELECT SUM(monto) FROM movimientos
#   WHERE persona='elias' AND moneda='ars' AND tipo='ingreso'
#
# Pero en vez de hacer 8 queries, hacemos una sola con GROUP BY y SUM
# condicional usando CASE WHEN. Más eficiente.
#
# Retorna: diccionario con las 4 claves originales + 4 totales en USD:
#   { 'elias_ars': float, 'elias_usd': float, 'mari_ars': float, 'mari_usd': float,
#     'elias_total_usd': float, 'mari_total_usd': float,
#     'ars_total_usd':   float, 'usd_total_usd':  float }
#
# Los totales en USD se calculan sumando la columna monto_usd (guardada al
# insertar/editar cada movimiento), por lo que reflejan la cotización histórica
# real al momento del movimiento y no dependen de la cotización actual.
# Se exponen dos agrupamientos:
#   - por persona: {elias_total_usd, mari_total_usd}
#   - por moneda origen: {ars_total_usd, usd_total_usd}
#     (útil para el gauge Total de la página de inicio).
#
def calcular_saldos(hasta=None):
    conn = conectar()
    cursor = conn.cursor()

    # Filtro opcional "saldos hasta una fecha" (inclusive). 'fecha' es TEXT
    # YYYY-MM-DD: la comparación de strings ISO ordena cronológicamente bien,
    # sin necesidad de parseo. hasta=None → sin filtro: agrega TODA la tabla
    # (comportamiento original intacto).
    # NOTA: filtro_fecha es un literal fijo (no dato de usuario); el valor
    # 'hasta' viaja por '?' parametrizado, así que no hay riesgo de inyección.
    filtro_fecha = ''
    params = []
    if hasta and re.match(r'^\d{4}-\d{2}-\d{2}$', hasta):
        filtro_fecha = 'WHERE fecha <= ?'
        params = [hasta]

    # Query 1: saldos por persona y moneda en moneda nativa (interfaz original).
    # Para ingresos de categoría "sueldo" se usa el factor_aplicado guardado en la fila.
    # Si factor_aplicado es NULL (movimientos viejos sin factor), se usa el monto completo.
    cursor.execute(f'''
        SELECT persona,
               moneda,
               SUM(CASE
                       WHEN tipo = 'ingreso' AND LOWER(COALESCE(categoria, '')) = 'sueldo'
                            AND factor_aplicado IS NOT NULL
                           THEN monto * factor_aplicado
                       WHEN tipo = 'ingreso'
                           THEN monto
                       ELSE 0
                   END) AS ingresos,
               SUM(CASE WHEN tipo = 'gasto' THEN monto + COALESCE(costo_envio, 0) ELSE 0 END) AS gastos
        FROM movimientos
        {filtro_fecha}
        GROUP BY persona, moneda
    ''', params)
    filas = cursor.fetchall()

    # Query 2: saldos acumulados en USD agrupados por persona Y moneda.
    # Si monto_usd es NULL (pendiente de backfill), se ignora esa fila en el SUM.
    # Se replica el mismo criterio de factor_aplicado para sueldos.
    # El costo_envio se prorratea: costo_envio * (monto_usd / monto).
    cursor.execute(f'''
        SELECT persona,
               moneda,
               SUM(CASE
                       WHEN tipo = 'ingreso' AND LOWER(COALESCE(categoria, '')) = 'sueldo'
                            AND factor_aplicado IS NOT NULL
                           THEN COALESCE(monto_usd, 0) * factor_aplicado
                       WHEN tipo = 'ingreso'
                           THEN COALESCE(monto_usd, 0)
                       ELSE 0
                   END) AS ingresos_usd,
               SUM(CASE WHEN tipo = 'gasto'
                           THEN COALESCE(monto_usd, 0)
                                + (COALESCE(costo_envio, 0) *
                                   CASE WHEN monto > 0 AND monto_usd IS NOT NULL
                                        THEN monto_usd / monto ELSE 0 END)
                       ELSE 0
                   END) AS gastos_usd
        FROM movimientos
        {filtro_fecha}
        GROUP BY persona, moneda
    ''', params)
    filas_usd = cursor.fetchall()

    conn.close()

    # Inicializamos los saldos en 0 (por si no hay movimientos aún)
    saldos = {
        'elias_ars':       0.0,
        'elias_usd':       0.0,
        'mari_ars':        0.0,
        'mari_usd':        0.0,
        'elias_total_usd': 0.0,
        'mari_total_usd':  0.0,
        'ars_total_usd':   0.0,  # suma de monto_usd de movimientos en ARS (gauge Total)
        'usd_total_usd':   0.0,  # suma de monto_usd de movimientos en USD (gauge Total)
    }

    for fila in filas:
        clave = f"{fila['persona']}_{fila['moneda']}"
        if clave in saldos:
            # saldo = ingresos acumulados - gastos acumulados
            saldos[clave] = fila['ingresos'] - fila['gastos']

    for fila in filas_usd:
        saldo_usd = (fila['ingresos_usd'] or 0.0) - (fila['gastos_usd'] or 0.0)

        clave_persona = f"{fila['persona']}_total_usd"
        if clave_persona in saldos:
            saldos[clave_persona] += saldo_usd

        clave_moneda = f"{fila['moneda']}_total_usd"
        if clave_moneda in saldos:
            saldos[clave_moneda] += saldo_usd

    return saldos


# =============================================================================
# FUNCIÓN: obtener_movimientos(persona, moneda, pagina, por_pagina)
# Propósito: Trae los movimientos, con filtros opcionales y paginación.
# =============================================================================
#
# Si pagina=None devuelve todos los registros (útil para /resumen).
# Si pagina es un entero devuelve la página solicitada.
#
# Retorna: (lista_de_filas, total_de_registros)
#
def obtener_movimientos(persona=None, moneda=None, pagina=None, por_pagina=20, mes=None, limite=None):
    conn = conectar()

    condiciones = []
    parametros  = []

    if persona:
        condiciones.append('persona = ?')
        parametros.append(persona)

    if moneda:
        condiciones.append('moneda = ?')
        parametros.append(moneda)

    if mes:
        condiciones.append("strftime('%Y-%m', fecha) = ?")
        parametros.append(mes)

    where = ('WHERE ' + ' AND '.join(condiciones)) if condiciones else ''

    # Total de registros para calcular páginas
    total = conn.execute(
        f'SELECT COUNT(*) FROM movimientos {where}', parametros
    ).fetchone()[0]

    query = f'''
        SELECT id, fecha, descripcion, persona, moneda, tipo, monto, categoria, costo_envio, factor_aplicado, cuota_numero, cuota_total, monto_usd, cotizacion_usd_aplicada
        FROM movimientos
        {where}
        ORDER BY fecha DESC, id DESC
    '''

    if limite is not None:
        query += f' LIMIT {int(limite)}'
    elif pagina is not None and por_pagina:
        offset = (pagina - 1) * por_pagina
        query += f' LIMIT {por_pagina} OFFSET {offset}'

    movimientos = conn.execute(query, parametros).fetchall()
    conn.close()
    return movimientos, total


# =============================================================================
# FUNCIÓN: agregar_movimiento(fecha, descripcion, persona, moneda, tipo, monto)
# Propósito: Inserta un nuevo movimiento en la base de datos.
# =============================================================================
#
# SQL equivalente:
#   INSERT INTO movimientos (fecha, descripcion, persona, moneda, tipo, monto)
#   VALUES ('2024-03-15', 'Sueldo', 'elias', 'ars', 'ingreso', 500000.0)
#
def agregar_movimiento(fecha, descripcion, persona, moneda, tipo, monto, categoria=None, costo_envio=None, factor_aplicado=None, cuota_numero=None, cuota_total=None, monto_usd=None, cotizacion_usd_aplicada=None):
    """
    Inserta un nuevo movimiento en la base de datos.

    Los parámetros monto_usd y cotizacion_usd_aplicada se calculan en app.py
    antes de llamar a esta función (ver lógica en /agregar y /editar).
      - Si moneda=='usd' → monto_usd=monto, cotizacion_usd_aplicada=None.
      - Si moneda=='ars' → monto_usd=monto/cotizacion, cotizacion_usd_aplicada=cotizacion.
    """
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO movimientos (fecha, descripcion, persona, moneda, tipo, monto, categoria, costo_envio, factor_aplicado, cuota_numero, cuota_total, monto_usd, cotizacion_usd_aplicada)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (fecha, descripcion, persona, moneda, tipo, monto, categoria, costo_envio, factor_aplicado, cuota_numero, cuota_total, monto_usd, cotizacion_usd_aplicada))
    # Los ? se reemplazan en orden con los valores de la tupla.
    # Esto evita SQL Injection: nunca armar el string SQL con format() o +

    conn.commit()   # Sin commit(), el INSERT no se guarda permanentemente
    nuevo_id = cursor.lastrowid
    conn.close()
    return nuevo_id


# =============================================================================
# FUNCIÓN: eliminar_movimiento(id)
# Propósito: Elimina un movimiento de la base de datos por su ID.
# =============================================================================
#
# SQL equivalente:
#   DELETE FROM movimientos WHERE id = 5
#
# ATENCIÓN: DELETE sin WHERE borraría TODA la tabla. El WHERE es crítico.
#
def eliminar_movimiento(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM movimientos WHERE id = ?', (id,))

    conn.commit()
    conn.close()


# =============================================================================
# FUNCIÓN: obtener_movimiento(id)
# Propósito: Devuelve un único movimiento por su ID (para el formulario editar).
# =============================================================================

def obtener_movimiento(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM movimientos WHERE id = ?', (id,))
    mov = cursor.fetchone()

    conn.close()
    return mov


# =============================================================================
# FUNCIÓN: editar_movimiento(id, fecha, descripcion, persona, moneda, tipo, monto)
# Propósito: Actualiza todos los campos de un movimiento existente.
# =============================================================================
#
# SQL equivalente:
#   UPDATE movimientos SET fecha=?, descripcion=?, ... WHERE id=?
#

def editar_movimiento(id, fecha, descripcion, persona, moneda, tipo, monto, categoria=None, costo_envio=None, monto_usd=None, cotizacion_usd_aplicada=None):
    """
    Actualiza un movimiento existente. Recalcula siempre monto_usd y
    cotizacion_usd_aplicada según la moneda/monto nuevos (pasados por app.py).
    """
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE movimientos
        SET fecha=?, descripcion=?, persona=?, moneda=?, tipo=?, monto=?, categoria=?, costo_envio=?, monto_usd=?, cotizacion_usd_aplicada=?
        WHERE id=?
    ''', (fecha, descripcion, persona, moneda, tipo, monto, categoria, costo_envio, monto_usd, cotizacion_usd_aplicada, id))

    conn.commit()
    conn.close()


# =============================================================================
# FUNCIONES: Gastos Fijos (movimientos recurrentes esperados cada mes)
# =============================================================================

def obtener_gastos_fijos(solo_activos=True):
    conn = conectar()
    if solo_activos:
        filas = conn.execute(
            'SELECT * FROM gastos_fijos WHERE activo = 1 ORDER BY descripcion'
        ).fetchall()
    else:
        filas = conn.execute(
            'SELECT * FROM gastos_fijos ORDER BY activo DESC, descripcion'
        ).fetchall()
    conn.close()
    return filas


def agregar_gasto_fijo(descripcion):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO gastos_fijos (descripcion) VALUES (?)',
        (descripcion,)
    )
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return nuevo_id


def editar_gasto_fijo(id, descripcion, activo):
    conn = conectar()
    conn.execute(
        'UPDATE gastos_fijos SET descripcion=?, activo=? WHERE id=?',
        (descripcion, activo, id)
    )
    conn.commit()
    conn.close()


def eliminar_gasto_fijo(id):
    conn = conectar()
    conn.execute('DELETE FROM gastos_fijos WHERE id = ?', (id,))
    conn.commit()
    conn.close()


def agregar_gasto_fijo_cuotas(descripcion, total_cuotas):
    """Crea un gasto fijo de tipo cuota (es_cuota=1), con cuota_actual=1."""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO gastos_fijos (descripcion, activo, es_cuota, total_cuotas, cuota_actual) VALUES (?, 1, 1, ?, 1)',
        (descripcion, total_cuotas)
    )
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return nuevo_id


def obtener_gasto_fijo_por_descripcion(descripcion):
    """Retorna el gasto fijo activo que coincide con la descripción (case-insensitive), o None."""
    conn = conectar()
    fijo = conn.execute(
        'SELECT * FROM gastos_fijos WHERE LOWER(descripcion) = LOWER(?) AND activo = 1 LIMIT 1',
        (descripcion,)
    ).fetchone()
    conn.close()
    return fijo


def avanzar_cuota(fijo_id):
    """Incrementa cuota_actual del gasto fijo. Si llega a total_cuotas, lo elimina."""
    conn = conectar()
    fijo = conn.execute('SELECT * FROM gastos_fijos WHERE id = ?', (fijo_id,)).fetchone()
    if not fijo:
        conn.close()
        return None
    nuevo_actual = (fijo['cuota_actual'] or 0) + 1
    if nuevo_actual >= fijo['total_cuotas']:
        conn.execute('DELETE FROM gastos_fijos WHERE id = ?', (fijo_id,))
    else:
        conn.execute('UPDATE gastos_fijos SET cuota_actual = ? WHERE id = ?', (nuevo_actual, fijo_id))
    conn.commit()
    conn.close()
    return nuevo_actual


def verificar_gastos_fijos(mes):
    """
    Para cada gasto fijo activo, busca si existe un movimiento en el mes dado
    con categoria='Fijo' y descripción coincidente (case-insensitive).
    Retorna lista de dicts con {id, descripcion, encontrado, monto, persona, moneda}.
    """
    conn = conectar()
    fijos = conn.execute(
        'SELECT * FROM gastos_fijos WHERE activo = 1 ORDER BY descripcion'
    ).fetchall()

    resultado = []
    for fijo in fijos:
        es_cuota = fijo['es_cuota'] if fijo['es_cuota'] else 0
        if es_cuota:
            # Para cuotas: buscar cualquier movimiento con esa descripción y cuota_numero en el mes
            mov = conn.execute('''
                SELECT monto, persona, moneda FROM movimientos
                WHERE LOWER(descripcion) = LOWER(?)
                  AND cuota_numero IS NOT NULL
                  AND strftime('%Y-%m', fecha) = ?
                LIMIT 1
            ''', (fijo['descripcion'], mes)).fetchone()
        else:
            mov = conn.execute('''
                SELECT monto, persona, moneda FROM movimientos
                WHERE LOWER(categoria) = 'fijo'
                  AND LOWER(descripcion) = LOWER(?)
                  AND strftime('%Y-%m', fecha) = ?
                LIMIT 1
            ''', (fijo['descripcion'], mes)).fetchone()

        resultado.append({
            'id':           fijo['id'],
            'descripcion':  fijo['descripcion'],
            'encontrado':   mov is not None,
            'monto':        float(mov['monto']) if mov else None,
            'persona':      mov['persona'] if mov else None,
            'moneda':       mov['moneda'] if mov else None,
            'es_cuota':     es_cuota,
            'cuota_actual': fijo['cuota_actual'] if fijo['cuota_actual'] else 0,
            'total_cuotas': fijo['total_cuotas'],
        })

    conn.close()
    return resultado
