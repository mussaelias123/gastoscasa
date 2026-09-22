# =============================================================================
# ARCHIVO: config.py
# =============================================================================
#
# Módulo de configuración centralizado.
# Lee y escribe config.json, que es la única fuente de verdad para
# todas las opciones del entorno (puerto, ngrok, primer inicio, etc.)
#
# =============================================================================

import json
import os

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

DEFAULTS = {
    "port": 5000,
    "first_run": True,
    "ngrok_enabled": False,
    "ngrok_authtoken": "",
    "ngrok_domain": "",
    "app_name": "Gastos Casa",
    "factor_sueldo": 0.7,
    # ── Lactancia (banco de leche) — editables desde el panel "Ajustes" de
    # /lactancia (NO desde Settings: la pantalla se trajo entera de la app
    # suelta, que configura el módulo desde adentro del propio módulo).
    # Vencimiento freezer = extracción + N meses; heladera = carga + N horas.
    # Los avisos definen la ventana "vence pronto" de cada ubicación.
    # freezar_hasta_horas: antigüedad máxima en heladera para poder pasar la
    # partida al freezer (regla de seguridad: leche muy refrigerada no se
    # congela). Pasado ese umbral, el checkbox de freezar se bloquea.
    # descongelada_horas: vida en heladera de una bolsa BAJADA del freezer
    # (leche que ya estuvo congelada y se descongela). Corre desde que se
    # baja, no desde la extracción. Guía típica: usar dentro de 24 h.
    "lactancia_freezer_meses":            6,
    "lactancia_heladera_horas":           48,
    "lactancia_descongelada_horas":       24,
    "lactancia_aviso_freezer_dias":       14,
    "lactancia_aviso_heladera_horas":     12,
    "lactancia_aviso_descongelada_horas":  6,
    "lactancia_freezar_hasta_horas":      24,
    # combinar_min_horas: horas mínimas que dos extracciones tienen que llevar
    # en la heladera para poder juntarse en una misma bolsita (las dos tienen
    # que estar a la misma temperatura). 0 = no verificar.
    "lactancia_combinar_min_horas":        3,
    # Capacidad de las bolsitas. Con `activa` en True no se deja cargar ni
    # combinar más de `ml` en una sola bolsita. Apagado por defecto: no todas
    # las bolsitas tienen el mismo tamaño y no queremos bloquear de entrada.
    "lactancia_bolsa_capacidad_activa":    False,
    "lactancia_bolsa_capacidad_ml":        150,
    # Pedir confirmación antes de cada acción que cierra una partida. Vivía en
    # el localStorage del navegador (clave `lac-confirmar`), o sea que cada
    # dispositivo tenía la suya; ahora es del servidor y vale para todos.
    "lactancia_pedir_confirmacion":        True,
    # Recordatorio nocturno de "bajar bolsitas" del freezer a la heladera (para
    # el día siguiente de jardín). activo = interruptor (modo jardín off hasta
    # que León arranque); hora = HH:MM local a partir de la cual avisa. Es un
    # aviso in-app (la campana); nunca bloquea nada.
    "lactancia_recordatorio_activo":      False,
    "lactancia_recordatorio_hora":        "21:00",
    # Días de jardín: todos por defecto, para que a nadie que no lo tocó le
    # cambie el comportamiento. "0"=lunes ... "6"=domingo.
    "lactancia_recordatorio_dias":        "0,1,2,3,4,5,6",
    # Perfil del bebé: nombre (se usa en los textos de la app) y fecha de
    # nacimiento (YYYY-MM-DD; habilita mostrar la edad y los cortes por mes de
    # vida). Deliberadamente NO se guarda peso ni estatura ni se estima cuánta
    # leche "debería" tomar: eso es terreno médico y la app no lo hace.
    "bebe_nombre":                        "León",
    "bebe_fecha_nacimiento":              "",
    # ── Rutina (rutina diaria de la familia) ───────────────────────────────
    # hora_noche / hora_amanecer: HH:MM locales. Cumplen doble función:
    #   1) el motor de ventanas de sueño usa hora_noche como tope del día
    #      (hasta ahí encadena siestas; después arranca el sueño nocturno);
    #   2) el fondo día/noche de la hoja decide con ellas cuándo sale y se
    #      pone el sol.
    # La familia, sus fechas de nacimiento y sus actividades NO viven acá:
    # van en las tablas rutina_miembros / rutina_actividades (database.py),
    # porque son datos del usuario y no configuración del entorno.
    "rutina_hora_noche":                  "20:00",
    "rutina_hora_amanecer":               "06:30",
    # Tarjeta de saludo el día del cumpleaños de cada miembro que tenga
    # fecha de nacimiento cargada. Interruptor por si molesta.
    "rutina_cumple_activo":               True,
    # ── Cotización USD oficial ──────────────────────────────────────────────
    # Se obtiene de dolarapi.com (módulo cotizacion.py) y se refresca 1 vez/día.
    # El 1500.0 es solo un bootstrap inicial; se sobrescribe en la primera
    # actualización exitosa.
    "cotizacion_valor":          1500.0,
    "cotizacion_fecha":          None,
    "cotizacion_ultimo_intento": None,
    "cotizacion_ok":             False,
    "google_client_id": "",
    "google_client_secret": "",
    "secret_key": "",
    # ── Bypass de login SOLO para DEV ───────────────────────────────────────
    # Si True, se saltea el login de Google, pero ÚNICAMENTE bajo triple cerrojo
    # (ver auth.py → require_login): auth_disabled + localhost + ngrok apagado.
    # En PROD: dejar SIEMPRE en False. Default seguro = False.
    "auth_disabled": False,
    # Con el bypass de arriba la sesión es un usuario falso (`dev@local`), que
    # no está en el mapa email→persona de auth.py. El módulo Personal necesita
    # saber de quién es la cuenta que muestra, así que en DEV la define esta
    # clave: cambiarla a "mari" permite probar la vista de Mari sin OAuth.
    # En PROD no se lee nunca (ahí la persona sale del email de Google).
    "persona_dev": "elias",
    # ── PWA: service worker y notificaciones push ──────────────────────────
    # DOS interruptores SEPARADOS a propósito: son dos modos de falla
    # distintos y hay que poder apagar uno sin el otro.
    #   sw_enabled   → si /sw.js sirve el service worker real o la LÁPIDA (el
    #                  SW suicida que borra cachés y se desregistra). Falla
    #                  típica: código o pantalla vieja cacheada en el celular.
    #   push_enabled → si la app ofrece notificaciones push del sistema.
    #                  Falla típica: avisos repetidos o a cualquier hora.
    # Se leen EN CALIENTE: `cargar_config()` va al disco en cada llamada, así
    # que apagarlos es editar config.json — sin deploy y sin reiniciar el
    # servicio. Eso es justamente lo que los hace un kill switch.
    # Default False los dos: la app arranca exactamente como estaba.
    "sw_enabled":   False,
    "push_enabled": False,
    # ── Push: par de claves VAPID + contacto ───────────────────────────────
    # VAPID es cómo el servidor le demuestra al servicio de push (FCM de
    # Google, Mozilla, el de Apple) que el aviso lo manda el dueño de la app y
    # no cualquiera. Es UN par de claves P-256, del SERVIDOR, no del usuario.
    #
    # SE GENERAN UNA SOLA VEZ, con `python TempScripts/generar_vapid.py`, y se
    # pegan a mano acá. Se tratan igual que `secret_key`: no se versionan, no
    # se loguean, no se muestran. Y como `secret_key`, REGENERARLAS ROMPE LO
    # QUE YA HAY — cambiar `secret_key` desloguea a todos; cambiar el par VAPID
    # invalida TODAS las suscripciones existentes, y encima en silencio: el
    # navegador sigue teniendo la suscripción vieja, el envío falla del lado
    # del servicio de push y el teléfono simplemente no recibe nada.
    #
    #   push_vapid_publica   → base64url del punto sin comprimir (65 bytes, 87
    #                          caracteres). Es la que el navegador necesita para
    #                          suscribirse (`applicationServerKey`), así que
    #                          VIAJA AL HTML a propósito: `base.html` la pone en
    #                          un data-attribute del <body>. Es pública por
    #                          definición; sola no sirve para mandar nada.
    #   push_vapid_secreta   → base64url del escalar privado (32 bytes, 43
    #                          caracteres). La come `pywebpush` tal cual.
    #                          Nombrada "secreta" y no "privada" a propósito:
    #                          que no se confunda de un vistazo con la pública
    #                          (y, de paso, cae sola bajo MARCADORES_SECRETOS).
    #   push_contacto_mailto → el `sub` del JWT: `mailto:alguien@dominio.com`,
    #                          CON el prefijo. Es a quién reclama el servicio de
    #                          push si la app se manda una macana. Apple lo
    #                          valida de verdad y es más estricto que FCM.
    #
    # Vacías por default: sin ellas nadie se suscribe y la app queda como está.
    "push_vapid_publica":   "",
    "push_vapid_secreta":   "",
    "push_contacto_mailto": "",
    # ── Backups de la base de datos ────────────────────────────────────────────
    # Ruta relativa a la carpeta del proyecto, o absoluta. Default: "backups".
    "backup_dir": "backups",
    # ── Paletas de colores — editables desde Settings ──────────────────────────
    # 23 variables base. Los aliases (--color-primario, etc.) siguen en style.css
    # como var() y NO se mueven aquí.
    "paleta_light": {
        "acento":         "#4f46e5",
        "acento-oscuro":  "#4338ca",
        "fondo":          "#f9fafb",
        "superficie":     "#ffffff",
        "texto":          "#111827",
        "texto-muted":    "#6b7280",
        "texto-invertido": "#ffffff",
        "borde":          "#e5e7eb",
        "exito":          "#10b981",
        "alerta":         "#f59e0b",
        "peligro":        "#ef4444",
        "exito-suave":    "#d1fae5",
        "alerta-suave":   "#fef3c7",
        "peligro-suave":  "#fee2e2",
        "persona-elias":  "#0284c7",
        "persona-mari":   "#7c3aed",
        "persona-leon":   "#4dd0e1",
        "moneda-ars":     "#74acdf",
        "moneda-usd":     "#3d8b37",
        "deco-1":         "#1f2937",
        "deco-2":         "#374151",
        "deco-3":         "#6b7280",
        "deco-4":         "#d1d5db",
    },
    "paleta_dark": {
        "acento":         "#6366f1",
        "acento-oscuro":  "#4f46e5",
        "fondo":          "#0f172a",
        "superficie":     "#1e293b",
        "texto":          "#e5e7eb",
        "texto-muted":    "#94a3b8",
        "texto-invertido": "#ffffff",
        "borde":          "#334155",
        "exito":          "#34d399",
        "alerta":         "#fbbf24",
        "peligro":        "#f87171",
        "exito-suave":    "#064e3b",
        "alerta-suave":   "#78350f",
        "peligro-suave":  "#7f1d1d",
        "persona-elias":  "#38bdf8",
        "persona-mari":   "#a78bfa",
        "persona-leon":   "#80deea",
        "moneda-ars":     "#8cbce6",
        "moneda-usd":     "#5cb85c",
        "deco-1":         "#0b1220",
        "deco-2":         "#1e293b",
        "deco-3":         "#64748b",
        "deco-4":         "#334155",
    },
}


# =============================================================================
# CLAVES SECRETAS — qué no puede salir de este módulo
# =============================================================================
#
# EL PROBLEMA: `inject_config()` (app.py) manda el dict ENTERO de config a
# TODOS los templates bajo la clave `cfg`. Ahí adentro viajan hoy
# `google_client_secret`, `secret_key` y `ngrok_authtoken`. Ningún template los
# imprime, así que hoy no se filtra nada — pero están a UN `{{ cfg }}` de
# distancia de aparecer en el HTML, y el HTML se lo lleva cualquiera que mire
# el código fuente de la página. No es un bug: es una mina puesta. Se saca
# justo antes de sumar una clave secreta más (`push_vapid_secreta`).
#
# POR QUÉ UN CRITERIO Y NO UNA LISTA DE NOMBRES: una lista hay que acordarse de
# actualizarla, y el día que alguien agrega una clave secreta y no la agrega a
# la lista, la clave sale al HTML sin que nada falle ni avise. El olvido es
# silencioso, que es la peor clase de olvido. Un criterio sobre el NOMBRE, en
# cambio, cubre sola a la clave nueva: alcanza con llamarla como ya se llaman
# todas las de esta app.
#
# QUÉ CUBRE HOY, sin tocar nada:
#     secret  → `secret_key`, `google_client_secret`, `push_vapid_secreta`
#     token   → `ngrok_authtoken`
# Las otras dos ("password", "clave_privada") no matchean ninguna clave actual:
# están para el nombre que todavía no existe.
#
# EL PRECIO, dicho en voz alta: una clave que NO sea secreta pero se llame con
# uno de estos fragmentos tampoco llega al template, y en Jinja eso no explota,
# renderiza vacío. Es el lado correcto del que fallar: un dato de más que falta
# se ve enseguida en la pantalla; un secreto de más que sobra no se ve nunca.
#
# REGLA para quien agregue una clave: si es un secreto, el nombre tiene que
# contener uno de estos fragmentos. Está congelado en `tests/test_cfg_secretos.py`.
MARCADORES_SECRETOS = ('secret', 'token', 'password', 'clave_privada')


def es_clave_secreta(clave):
    """True si el NOMBRE de la clave la marca como secreta (ver arriba)."""
    nombre = str(clave).lower()
    return any(marcador in nombre for marcador in MARCADORES_SECRETOS)


def sin_secretos(cfg):
    """
    Copia de `cfg` sin las claves secretas. Es lo que se le pasa a los
    templates (app.py → inject_config).

    COSTO: es una comprensión de dict sobre ~45 claves, del orden del
    microsegundo. Corre en cada render, sí — pero pegada a `cargar_config()`,
    que en ese mismo render ABRE UN ARCHIVO DEL DISCO y lo parsea con
    `json.load`. Al lado de eso esto no se mide: cachearlo agregaría un
    invalidador nuevo (y el lector en caliente de `sw_enabled` depende
    justamente de que no haya caché) a cambio de nada.

    Copia PLANA a propósito: los valores anidados (`paleta_light`,
    `paleta_dark`) se comparten con el dict original, que `cargar_config()`
    arma nuevo en cada llamada. No hay secretos anidados y nadie muta el cfg
    del render.
    """
    return {k: v for k, v in cfg.items() if not es_clave_secreta(k)}


# Rangos válidos de los parámetros numéricos del panel "Ajustes" de Lactancia.
# Se validan en el servidor (POST /api/lactancia/config) además del min/max del
# HTML: el navegador es una comodidad, no una garantía. Las claves son las
# cortas de LAC_PARAMS_NUM (app.py), no las de config.json.
LIMITES_LACTANCIA = {
    'freezer_meses':            (1, 24),
    'heladera_horas':           (1, 168),
    'descongelada_horas':       (1, 72),
    'aviso_freezer_dias':       (1, 90),
    'aviso_heladera_horas':     (1, 72),
    'aviso_descongelada_horas': (1, 48),
    'freezar_hasta_horas':      (1, 72),
    'combinar_min_horas':       (0, 24),
    'bolsa_capacidad_ml':       (10, 2000),
}


def cargar_config(ruta=None):
    """Lee el archivo de config y retorna un dict. Usa defaults para claves faltantes."""
    if ruta is None:
        ruta = _DEFAULT_CONFIG_PATH
    cfg = dict(DEFAULTS)
    if os.path.exists(ruta):
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                datos = json.load(f)
            cfg.update(datos)
            # Paletas: merge por clave. Si config.json trae una paleta guardada
            # vieja (menos claves que DEFAULTS), las claves nuevas de DEFAULTS
            # sobreviven (ej. texto-invertido agregado en 2026-07).
            for paleta in ('paleta_light', 'paleta_dark'):
                base = dict(DEFAULTS.get(paleta, {}))
                base.update(datos.get(paleta) or {})
                cfg[paleta] = base
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def guardar_config(data, ruta=None):
    """Escribe el dict `data` en el archivo de config."""
    cfg = cargar_config(ruta)
    cfg.update(data)
    if ruta is None:
        ruta = _DEFAULT_CONFIG_PATH
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def es_primer_inicio():
    """Retorna True si first_run está en True en config.json."""
    return cargar_config().get('first_run', True)
