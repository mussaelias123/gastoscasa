# =============================================================================
# ARCHIVO: tests/test_cfg_secretos.py
# =============================================================================
#
# Tests del RECORTE de `cfg`: qué de la configuración llega a los templates y
# qué no.
#
# POR QUE EXISTE ESTE ARCHIVO
#   `inject_config()` (app.py) es un context processor: le pasa `cfg` a TODOS
#   los templates de la app, en TODOS los renders. Hasta ahora le pasaba el
#   dict ENTERO de config.json — con `secret_key`, `google_client_secret` y
#   `ngrok_authtoken` adentro. Ningun template los imprimia, asi que no se
#   filtraba nada: era una mina puesta, no un incendio. Un `{{ cfg }}` de mas
#   —o un `{% for k, v in cfg.items() %}` en una pantalla de debug— y los
#   secretos salian al HTML, que se lee con click derecho.
#
#   El recorte (config.sin_secretos) lo hace IMPOSIBLE en vez de improbable.
#   Pero un recorte es codigo silencioso: si alguien lo saca, lo puentea o le
#   agrega una clave secreta que el criterio no cubre, NADA falla. La app da
#   200 en todas las paginas, se ve igual, y el secreto viaja.
#
#   Por eso se congelan aca las cuatro cosas de las que depende:
#     1. El criterio (config.py → MARCADORES_SECRETOS) cubre las claves
#        secretas de hoy, y cubre sola a la que se agregue manana.
#     2. Lo que los templates SI necesitan sigue llegando — un recorte que se
#        lleva puesta la paleta tambien es un bug, solo que uno que se ve.
#     3. Ninguna ruta puentea el recorte pasandole su propio `cfg` al
#        `render_template` (es lo que hacian /gastos y /settings).
#     4. EL TEST QUE IMPORTA: el HTML SERVIDO no contiene ningun valor secreto.
#        Es el unico que atrapa la regresion de verdad, porque no mira el
#        camino sino el resultado: no importa por donde se cuele el secreto, si
#        llega al navegador este test se pone rojo.
#
#   Si uno de estos tests falla, la pregunta NO es "como lo hago pasar": es
#   "que secreto le estoy mandando al navegador".
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_cfg_secretos -v
#
# =============================================================================

import os
import re
import sys
import unittest
import unittest.mock

from flask import template_rendered

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
import config  # noqa: E402


# Las claves secretas que existen HOY en DEFAULTS. Esta lista esta a mano A
# PROPOSITO, y es la unica de todo el esquema: no la usa el codigo (el codigo
# usa el criterio de config.py), la usan estos tests como contraparte. Si
# alguien agrega una clave secreta y este archivo no se entera, el test de mas
# abajo se pone rojo y lo obliga a mirar si el criterio la cubre.
SECRETAS_DE_HOY = {
    'secret_key',
    'google_client_secret',
    'ngrok_authtoken',
    'push_vapid_secreta',
}

# TODAS las claves de DEFAULTS, no solo las secretas. El criterio por nombre
# no adivina: `apikey_mercadopago` es un secreto de verdad y sobrevive el
# recorte. Congelando el conjunto entero, agregar CUALQUIER clave pone el
# test en rojo y obliga a clasificarla a mano. Es la unica forma de cerrar
# ese agujero sin inventar un criterio que adivine.
CLAVES_DE_HOY = {
    'app_name',
    'auth_disabled',
    'backup_dir',
    'bebe_fecha_nacimiento',
    'bebe_nombre',
    'cotizacion_fecha',
    'cotizacion_ok',
    'cotizacion_ultimo_intento',
    'cotizacion_valor',
    'factor_sueldo',
    'first_run',
    'google_client_id',
    'google_client_secret',
    'lactancia_aviso_descongelada_horas',
    'lactancia_aviso_freezer_dias',
    'lactancia_aviso_heladera_horas',
    'lactancia_bolsa_capacidad_activa',
    'lactancia_bolsa_capacidad_ml',
    'lactancia_combinar_min_horas',
    'lactancia_descongelada_horas',
    'lactancia_freezar_hasta_horas',
    'lactancia_freezer_meses',
    'lactancia_heladera_horas',
    'lactancia_pedir_confirmacion',
    'lactancia_recordatorio_activo',
    'lactancia_recordatorio_dias',
    'lactancia_recordatorio_hora',
    'ngrok_authtoken',
    'ngrok_domain',
    'ngrok_enabled',
    'paleta_dark',
    'paleta_light',
    'persona_dev',
    'port',
    'push_contacto_mailto',
    'push_enabled',
    'push_silencio_desde',
    'push_silencio_hasta',
    'push_vapid_publica',
    'push_vapid_secreta',
    'rutina_cumple_activo',
    'rutina_hora_amanecer',
    'rutina_hora_noche',
    'secret_key',
    'sw_enabled',
}

# Lo que los templates de hoy leen de `cfg` (grep de templates/). Si el recorte
# se lleva puesta una de estas, la app se rompe de formas raras y calladas: sin
# `paleta_light` no hay colores, sin `app_name` el input de Settings sale vacio
# y guarda vacio.
NECESARIAS_EN_TEMPLATES = (
    'app_name',           # base.html (banner DEV) + settings.html (input)
    'first_run',          # gastos.html (cartel de primer inicio)
    'factor_sueldo',      # settings.html (input)
    'cotizacion_valor',   # settings.html
    'cotizacion_fecha',
    'cotizacion_ok',
    'cotizacion_ultimo_intento',
    'paleta_light',       # base.html (<style> inyectado) + settings.html
    'paleta_dark',
    'sw_enabled',         # base.html (registrar el SW o barrerlo)
    'push_vapid_publica',  # base.html (data-attribute; es PUBLICA a proposito)
)

# Valores canario: no son secretos de verdad, son cadenas inventadas que se le
# meten a la config durante el test para despues buscarlas en el HTML. Se usan
# cadenas raras y unicas para que un match no pueda ser casualidad.
CANARIOS = {
    'secret_key':           'CANARIO-SECRETKEY-ZZQ1',
    'google_client_secret': 'CANARIO-OAUTHSECRET-ZZQ2',
    'ngrok_authtoken':      'CANARIO-NGROKTOKEN-ZZQ3',
    'push_vapid_secreta':   'CANARIO-VAPIDSECRETA-ZZQ4',
}

# La clave publica NO es un canario: es lo que TIENE que aparecer en el HTML.
PUBLICA_DE_PRUEBA = 'CLAVEPUBLICADEPRUEBA-ZZQ5'

# Paginas que se sirven con base.html. Son las tres que usan `cfg` (base,
# gastos y settings) mas el Inicio, que arrastra base.html igual.
PAGINAS = ('/', '/gastos', '/settings')


def _cfg_con(**cambios):
    """
    Devuelve un `cargar_config` falso: la config de verdad con las claves que
    se pidan pisadas. Se parchea la funcion y no el archivo, para no tocar el
    config.json real de la maquina donde corren los tests. (Mismo helper que
    tests/test_sw.py; se repite a proposito para que cada archivo se pueda leer
    solo.)
    """
    real = config.cargar_config

    def falso(ruta=None):
        cfg = real(ruta)
        cfg.update(cambios)
        return cfg

    return falso


def _cfg_de_prueba():
    """La config real + los canarios + la publica de prueba + el login abierto.

    `auth_disabled=True` y `ngrok_enabled=False` van explicitos para que la
    suite tambien pase en el clon de PROD, donde el bypass esta apagado y las
    paginas redirigirian al login (y un 302 no tiene HTML que revisar).
    """
    return _cfg_con(auth_disabled=True, ngrok_enabled=False,
                    push_vapid_publica=PUBLICA_DE_PRUEBA, **CANARIOS)


# =============================================================================
# 1. EL CRITERIO
# =============================================================================

class TestCriterioDeClaveSecreta(unittest.TestCase):

    def test_saca_las_secretas_de_hoy(self):
        recortado = config.sin_secretos(config.DEFAULTS)
        for clave in SECRETAS_DE_HOY:
            with self.subTest(clave=clave):
                self.assertIn(clave, config.DEFAULTS,
                              'la clave ya no existe en DEFAULTS: actualizar '
                              'SECRETAS_DE_HOY en este archivo')
                self.assertNotIn(clave, recortado)

    def test_las_secretas_de_hoy_son_exactamente_estas(self):
        """
        EL CHECKPOINT. Congela el conjunto de claves que el criterio se lleva.
        Falla en los dos sentidos, y los dos hay que mirarlos:

          · Aparece una clave de mas → alguien agrego un secreto. Bien: el
            criterio la cubrio sola. Sumarla a SECRETAS_DE_HOY y seguir.
          · Aparece una clave de mas que NO es un secreto → el criterio se esta
            comiendo un dato que los templates podrian querer. Renombrar la
            clave (no aflojar el criterio).
          · Falta una → se renombro un secreto a un nombre que el criterio ya
            no reconoce, y ese secreto esta viajando al HTML. Es el caso grave.
        """
        detectadas = {k for k in config.DEFAULTS if config.es_clave_secreta(k)}
        self.assertEqual(detectadas, SECRETAS_DE_HOY)

    def test_ninguna_clave_de_defaults_esconde_un_secreto_adentro(self):
        """
        EL RECORTE ES PLANO: mira solo las claves de primer nivel. Hoy alcanza
        porque ningun valor de DEFAULTS es un dict con secretos adentro, pero
        nada lo sostenia — y la forma mas probable que tome la config del push
        cuando crezca es justo un bloque agrupado:

            "push": {"vapid_secreta": "...", "contacto": "..."}

        Ahi el nombre de primer nivel es `push`, no matchea ningun marcador, y
        el sub-dict entero cruza a Jinja con la secreta adentro. Vuelve la mina
        exacta que este modulo vino a sacar, y ni el criterio ni el checkpoint
        de arriba se enteran.

        Este test NO hace recursivo el recorte: obliga a no anidar secretos,
        que es mas barato y ataca lo mismo.
        """
        for clave, valor in config.DEFAULTS.items():
            if not isinstance(valor, dict):
                continue
            adentro = [k for k in valor if config.es_clave_secreta(k)]
            self.assertEqual(
                adentro, [],
                f'DEFAULTS["{clave}"] es un dict y tiene {adentro} adentro. '
                f'El recorte es PLANO: eso viaja entero a los templates. '
                f'Sacar el secreto a primer nivel (ej. "{clave}_secreta").')

    def test_toda_clave_nueva_de_defaults_hay_que_clasificarla(self):
        """
        EL AGUJERO DEL CRITERIO POR NOMBRE, cerrado por el unico lado que se
        puede: `apikey_mercadopago` o `credencial_afip` son secretos de verdad
        con nombres que no siguen la convencion, y SOBREVIVEN el recorte. El
        checkpoint de arriba no los agarra: no desaparecio ninguna secreta
        conocida, aparecio una clave nueva que el test no considera secreta.

        Asi que se congelan TODAS las claves de DEFAULTS. Agregar una pone
        este test en rojo y obliga a mirarla de frente: si es un secreto, hay
        que nombrarla con un marcador (regla 4 de CONTEXT_CONFIG.md); si no,
        sumarla a la lista de aca abajo y seguir.
        """
        self.assertEqual(
            set(config.DEFAULTS), CLAVES_DE_HOY,
            'Cambio el conjunto de claves de DEFAULTS. Si la clave nueva es un '
            'SECRETO, renombrala para que caiga bajo MARCADORES_SECRETOS '
            '(regla 4 de CONTEXT_CONFIG.md) — el criterio por nombre no '
            'adivina. Si no lo es, sumala a CLAVES_DE_HOY en este archivo.')

    def test_cubre_sola_a_la_clave_que_todavia_no_existe(self):
        """
        LA razon de ser del criterio, y por que no es una lista negra de
        nombres: una lista hay que acordarse de actualizarla, y el olvido no
        falla, filtra. Estas claves no existen en ningun lado y ya estan
        cubiertas, sin tocar una linea de codigo.
        """
        inventadas = ('mercadopago_access_token', 'smtp_password',
                      'whatsapp_api_secret', 'firebase_clave_privada')
        recortado = config.sin_secretos({k: 'x' for k in inventadas})
        self.assertEqual(recortado, {})

    def test_no_se_lleva_puesto_lo_que_los_templates_necesitan(self):
        """La contracara: un recorte que recorta de mas tambien rompe la app."""
        recortado = config.sin_secretos(config.DEFAULTS)
        for clave in NECESARIAS_EN_TEMPLATES:
            with self.subTest(clave=clave):
                self.assertIn(clave, recortado)
                self.assertEqual(recortado[clave], config.DEFAULTS[clave])

    def test_la_publica_de_vapid_no_es_secreta(self):
        """
        Las dos claves del par se parecen de nombre y hacen cosas opuestas. Si
        el criterio se llevara tambien la publica, el navegador se quedaria sin
        con que suscribirse — y la falla seria "el push no anda", sin mas pista.
        """
        self.assertFalse(config.es_clave_secreta('push_vapid_publica'))
        self.assertTrue(config.es_clave_secreta('push_vapid_secreta'))

    def test_no_muta_el_original(self):
        original = dict(config.DEFAULTS)
        config.sin_secretos(config.DEFAULTS)
        self.assertEqual(config.DEFAULTS, original)


# =============================================================================
# 2. LO QUE SALE DEL CONTEXT PROCESSOR
# =============================================================================

class TestContextProcessor(unittest.TestCase):

    def test_el_cfg_inyectado_no_trae_secretos(self):
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_de_prueba()):
            with app_module.app.test_request_context('/'):
                cfg = app_module.inject_config()['cfg']
        for clave in SECRETAS_DE_HOY:
            with self.subTest(clave=clave):
                self.assertNotIn(clave, cfg)

    def test_el_cfg_inyectado_trae_lo_necesario(self):
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_de_prueba()):
            with app_module.app.test_request_context('/'):
                cfg = app_module.inject_config()['cfg']
        for clave in NECESARIAS_EN_TEMPLATES:
            with self.subTest(clave=clave):
                self.assertIn(clave, cfg)

    def test_una_clave_recortada_no_explota_en_jinja(self):
        """
        POR QUE ESTE TEST: el recorte saca claves de un dict, y un template que
        pida una clave que no esta tiene que renderizar vacio, NO tirar 500.
        Es asi porque el entorno Jinja de la app usa el `Undefined` por
        defecto; con `StrictUndefined` —un cambio de una linea que alguien
        podria hacer buscando "mas seguridad"— cada `{{ cfg.secret_key }}`
        viejo pasaria a ser un error 500 en produccion.
        """
        plantilla = app_module.app.jinja_env.from_string(
            '[{{ cfg.secret_key }}][{{ cfg.ngrok_authtoken }}]'
            '[{% if cfg.google_client_secret %}HAY{% endif %}]')
        self.assertEqual(plantilla.render(cfg=config.sin_secretos(config.DEFAULTS)),
                         '[][][]')


# =============================================================================
# 3. QUE NINGUNA RUTA PUENTEE EL RECORTE
# =============================================================================

class TestNadieSePasaElRecorte(unittest.TestCase):
    """
    POR QUE ESTE BLOQUE: un `render_template('x.html', cfg=cfg)` PISA el `cfg`
    del context processor con el dict completo. Es exactamente lo que hacian
    /gastos y /settings, y es un puenteo invisible: la pagina anda igual, el
    recorte sigue escrito en app.py, y el secreto viaja lo mismo.

    Se mira el contexto FINAL de cada render (senal `template_rendered` de
    Flask), que es lo que Jinja tiene realmente a mano: ahi ya se aplicaron
    tanto el context processor como los kwargs de la ruta.
    """

    def setUp(self):
        self.client = app_module.app.test_client()
        self.contextos = []

        def registrar(sender, template, context, **extra):
            self.contextos.append((template.name, context))

        self.registrar = registrar
        template_rendered.connect(registrar, app_module.app)
        self.addCleanup(template_rendered.disconnect, registrar, app_module.app)

    def test_ninguna_pagina_renderiza_con_un_cfg_completo(self):
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_de_prueba()):
            for url in PAGINAS:
                self.client.get(url)

        self.assertTrue(self.contextos, 'no se renderizo ningun template')
        for nombre, contexto in self.contextos:
            cfg = contexto.get('cfg')
            if cfg is None:
                continue
            for clave in SECRETAS_DE_HOY:
                with self.subTest(template=nombre, clave=clave):
                    self.assertNotIn(
                        clave, cfg,
                        f'{nombre} recibe un cfg con {clave}: alguna ruta le '
                        f'esta pasando `cfg=` a mano y saltea el recorte')


# =============================================================================
# 4. EL HTML SERVIDO (el test que atrapa la regresion de verdad)
# =============================================================================

class TestElHtmlServido(unittest.TestCase):

    def setUp(self):
        self.client = app_module.app.test_client()

    def _html(self, url):
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_de_prueba()):
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200,
                         f'{url} no sirvio una pagina ({r.status_code})')
        return r.get_data(as_text=True)

    def test_ninguna_pagina_contiene_un_valor_secreto(self):
        """
        EL test. No mira por donde viaja el secreto: mira si llego al
        navegador. Cualquier camino nuevo que alguien invente para filtrarlo
        —un kwarg, un `{{ cfg }}`, un JSON embebido, un data-attribute— cae
        aca.
        """
        for url in PAGINAS:
            html = self._html(url)
            for clave, canario in CANARIOS.items():
                with self.subTest(url=url, clave=clave):
                    self.assertNotIn(canario, html,
                                     f'{url} imprimio el valor de {clave} en el HTML')

    def test_los_comentarios_de_jinja_tampoco_salen(self):
        """
        `base.html` NOMBRA a `push_vapid_secreta` en un comentario `{# #}` para
        explicar por que no esta. Los comentarios de Jinja no se renderizan, y
        conviene tenerlo probado: si alguien los pasa a comentarios HTML
        `<!-- -->`, empiezan a viajar al navegador.
        """
        html = self._html('/gastos')
        self.assertNotIn('push_vapid_secreta', html)
        self.assertNotIn('MARCADORES_SECRETOS', html)

    # -- La otra mitad: lo que SI tiene que estar ----------------------------

    def test_las_paginas_siguen_recibiendo_su_config(self):
        """
        POR QUE ESTE TEST: /gastos y /settings pasaron de recibir `cfg` como
        kwarg a recibirlo del context processor. Si eso hubiera quedado mal,
        Jinja no protesta: renderiza vacio. El input de Settings saldria en
        blanco y, al guardar, escribiria ese blanco en config.json.
        """
        with unittest.mock.patch.object(
                config, 'cargar_config',
                _cfg_con(auth_disabled=True, ngrok_enabled=False,
                         app_name='NombreDePrueba-ZZQ6', factor_sueldo=0.42,
                         push_vapid_publica=PUBLICA_DE_PRUEBA, **CANARIOS)):
            settings = self.client.get('/settings').get_data(as_text=True)
            gastos = self.client.get('/gastos').get_data(as_text=True)

        self.assertIn('NombreDePrueba-ZZQ6', settings, 'settings.html perdio app_name')
        self.assertIn('0.42', settings, 'settings.html perdio factor_sueldo')
        # La paleta viaja por el <style> de base.html, o sea que esta en las dos.
        for nombre, html in (('settings', settings), ('gastos', gastos)):
            with self.subTest(pagina=nombre):
                self.assertIn('--color-acento:', html, 'se perdio la paleta')

    def test_la_clave_publica_de_vapid_viaja_en_el_body(self):
        """
        Es publica por definicion: el navegador la necesita para suscribirse.
        Va en un data-attribute del <body> de base.html, asi que tiene que
        estar en TODAS las paginas.
        """
        for url in PAGINAS:
            with self.subTest(url=url):
                self.assertIn('data-push-vapid="%s"' % PUBLICA_DE_PRUEBA,
                              self._html(url))

    def test_sin_claves_generadas_el_atributo_sale_vacio(self):
        """
        EL CASO DE HOY: nadie genero todavia el par VAPID. El atributo tiene
        que salir igual y vacio (`dataset.pushVapid === ''`, falso), que es la
        senal de "push no configurado". Sin `default('', true)` un `None` en
        config.json renderizaria el texto "None", que es un string NO vacio:
        el codigo de suscripcion lo tomaria por una clave y fallaria adentro
        del navegador, lejos de aca.
        """
        for valor in ('', None):
            with self.subTest(valor=valor):
                with unittest.mock.patch.object(
                        config, 'cargar_config',
                        _cfg_con(auth_disabled=True, ngrok_enabled=False,
                                 push_vapid_publica=valor)):
                    html = self.client.get('/gastos').get_data(as_text=True)
                self.assertIn('data-push-vapid=""', html)
                self.assertNotIn('None', html.split('<body', 1)[1].split('>', 1)[0])


# =============================================================================
# 5. LOS TEMPLATES NO NOMBRAN NINGUNA CLAVE SECRETA
# =============================================================================

class TestLosTemplatesNoPidenSecretos(unittest.TestCase):
    """
    El recorte deja de ser gratis el dia que un template necesite algo que se
    recorto: ahi no hay error, hay un vacio. Este test lo detecta en el codigo
    fuente, antes de que alguien lo vea en pantalla.
    """

    def test_ningun_template_lee_una_clave_secreta_del_cfg(self):
        raiz = os.path.join(ROOT_DIR, 'templates')
        archivos = [os.path.join(raiz, n) for n in os.listdir(raiz)
                    if n.endswith('.html')]
        self.assertTrue(archivos, 'no se encontro ningun template')

        for ruta in archivos:
            with open(ruta, 'r', encoding='utf-8') as f:
                texto = f.read()
            for clave in SECRETAS_DE_HOY:
                patron = r"cfg(\.%s\b|\[\s*['\"]%s['\"]\s*\])" % (clave, clave)
                with self.subTest(template=os.path.basename(ruta), clave=clave):
                    self.assertIsNone(
                        re.search(patron, texto),
                        f'{os.path.basename(ruta)} lee cfg.{clave}, que ya no '
                        f'llega a los templates: va a renderizar vacio')


if __name__ == '__main__':
    unittest.main(verbosity=2)
