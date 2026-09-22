# =============================================================================
# ARCHIVO: TempScripts/generar_vapid.py
# =============================================================================
#
# QUÉ HACE:
#   Genera EL par de claves VAPID de esta app —una sola vez en la vida— y lo
#   imprime en los dos formatos exactos que hay que pegar en `config.json`:
#
#       push_vapid_publica   → base64url del punto sin comprimir (65 bytes
#                              crudos → 87 caracteres). Es lo que come
#                              `pushManager.subscribe({applicationServerKey})`
#                              en el navegador.
#       push_vapid_secreta   → base64url del escalar privado (32 bytes → 43
#                              caracteres). Es lo que come `pywebpush`
#                              (`webpush(..., vapid_private_key=...)`, que lo
#                              pasa por `py_vapid.Vapid.from_string`).
#
#   Y antes de imprimir nada hace una FIRMA DE PRUEBA con esas MISMAS dos
#   cadenas: arma un Vapid desde el string privado, firma un JWT de mentira y
#   lo verifica con el string público. Si eso pasa, el par sirve. Es el paso
#   que evita el error clásico de la primera integración: claves en el formato
#   equivocado (PEM, DER, base64 común en vez de base64url, el punto
#   comprimido de 33 bytes en vez de los 65 sin comprimir) que se pegan igual
#   en config.json y recién fallan meses después, contra el servicio de push.
#
# QUÉ NO HACE: NO escribe `config.json`, ni ningún archivo, ni ningún log.
#   Imprime y se va. Las claves se pegan A MANO. Es a propósito: un script que
#   escribe la config puede pisar un par que ya estaba en uso, y este es
#   justamente el archivo del que no hay vuelta atrás.
#
# POR QUÉ ES UN SCRIPT ONE-SHOT (TempScripts/, regla 3 de CLAUDE.md):
#   La app NO genera claves en runtime. Esto se corre a mano UNA vez por
#   entorno, se pegan las dos cadenas en `config.json` y el archivo no se
#   vuelve a tocar nunca más.
#
# CÓMO SE CORRE:
#       pip install -r requirements.txt          (trae pywebpush + py-vapid)
#       python TempScripts/generar_vapid.py
#       python TempScripts/generar_vapid.py mailto:elias@ejemplo.com
#
#   El argumento opcional es el `sub` del JWT (a quién reclama el servicio de
#   push si la app molesta). Si no se pasa, se usa el `push_contacto_mailto`
#   de config.json, y si tampoco está, un placeholder SOLO para la prueba.
#
# ⚠ ESTO SE CORRE UNA SOLA VEZ. LEER ESTO ANTES DE CORRERLO DE NUEVO:
#   Cada corrida genera un par NUEVO y DISTINTO — no hay forma de "recuperar"
#   el anterior. Y pegar un par nuevo sobre uno que ya estaba en uso INVALIDA
#   TODAS LAS SUSCRIPCIONES EXISTENTES: cada navegador guardó la clave pública
#   vieja cuando se suscribió, el servicio de push rechaza los envíos firmados
#   con la nueva (403 VapidError) y los teléfonos dejan de recibir avisos.
#   Es el mismo trato que `secret_key` (cambiarla desloguea a todos), con un
#   agravante: ESTE FALLO ES SILENCIOSO. La app no se rompe, no tira error en
#   pantalla, no hay nada raro que mirar; simplemente no llega ningún aviso, y
#   nadie se entera hasta que alguien pregunta por qué no le suena el teléfono.
#   Para volver atrás habría que re-suscribir a mano cada dispositivo.
#
#   Por eso el script ABORTA si `config.json` ya tiene `push_vapid_publica`
#   cargada. Para forzarlo (sabiendo lo de arriba) hay que pasar `--forzar`.
#
# HIGIENE: las claves salen por pantalla. No mandar la corrida a un archivo, no
#   pegarla en un chat, no dejarla en el historial de una terminal compartida.
#   La secreta va SOLO a `config.json`, que está en `.gitignore`.
# =============================================================================

import base64
import json
import os
import sys
import time

# Consola de Windows: una consola en cp1252 no dibuja los caracteres de los
# recuadros sin esto. (No: esto NO es una invitación a mandar la salida a un
# archivo — ver HIGIENE arriba. La secreta se lee de la pantalla y se pega.)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    from py_vapid import Vapid02 as Vapid, VapidException
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print('FALTA LA LIBRERÍA. Correr primero:  pip install -r requirements.txt')
    raise SystemExit(1)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# Placeholder SOLO para la firma de prueba. `py_vapid` valida el formato del
# `sub` (tiene que ser un `mailto:` con dominio de verdad), así que sin uno no
# se puede probar nada. Nunca sale de esta corrida.
MAILTO_PRUEBA = 'mailto:nadie@ejemplo.com'

# El servicio de push de Google. Acá no se le manda NADA: es solo el `aud` que
# el JWT tiene que declarar para poder firmarse.
AUD_PRUEBA = 'https://fcm.googleapis.com'

RAYA = '─' * 72


def b64url(datos):
    """base64url SIN padding: el formato de todo lo que viaja en Web Push."""
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode('ascii')


def _exigir(condicion, motivo):
    """
    Un `assert` con otro nombre, y a propósito: `python -O` (o un
    PYTHONOPTIMIZE que venga del entorno) borra los `assert` del bytecode. Y
    toda la verificación del par vive en esos chequeos: sin ellos el script
    imprimiría "probado y funcionando" sobre una clave que el navegador
    rechaza, que es exactamente el error confuso que este script existe para
    evitar — pero ahora con el sello de aprobado puesto encima.
    """
    if not condicion:
        print(f'\n  ERROR: {motivo}')
        print('  El par NO sirve. No pegar nada en config.json.\n')
        raise SystemExit(1)


def leer_config():
    """
    config.json como dict, o {} si NO EXISTE. No escribe nada.

    Si el archivo existe pero no se puede leer, esto ABORTA en vez de devolver
    {}. Los dos casos parecen iguales desde acá y no lo son: con {} la guarda
    de la segunda corrida se abre sola, justo en el escenario para el que
    existe. Y ese escenario es el realista — alguien pega las claves a mano
    (que es lo que este script le manda a hacer), se le va una coma, y vuelve a
    correrlo para ver qué pasó. En vez del cartel de "ya tenés un par", le
    saldría uno nuevo con cara de todo bien.
    """
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f'\n  ERROR: {CONFIG_FILE} existe pero no se puede leer ({e}).')
        print('  No se genera nada: primero hay que saber si ya hay un par cargado.')
        print('  Arreglá el JSON y volvé a correr esto.\n')
        raise SystemExit(1)


def abortar_si_ya_hay_claves(cfg, forzar):
    """
    La red de seguridad contra la segunda corrida. Mira SOLO la clave pública
    (la secreta no se lee, no se imprime y no se compara: no hay ninguna razón
    para que este script la toque).
    """
    if not (cfg.get('push_vapid_publica') or '').strip():
        return
    if forzar:
        print('⚠ --forzar: ya había claves en config.json y se generan otras igual.')
        print('  Todas las suscripciones que existan quedan muertas. En silencio.\n')
        return
    print(RAYA)
    print('NO SE GENERÓ NADA. config.json YA TIENE UN PAR DE CLAVES VAPID.')
    print(RAYA)
    print('Generar otro par invalida TODAS las suscripciones que existan hoy:')
    print('cada navegador se suscribió con la clave pública vieja y el servicio')
    print('de push rechaza lo que se firme con la nueva. No avisa nada: los')
    print('avisos simplemente dejan de llegar.')
    print('')
    print('Si igual hay que hacerlo (se filtró la secreta, entorno nuevo):')
    print('    python TempScripts/generar_vapid.py --forzar')
    print('y después hay que re-suscribir a mano cada dispositivo.')
    raise SystemExit(1)


def generar():
    """Un par P-256 nuevo → (publica_b64url, secreta_b64url)."""
    vapid = Vapid()
    vapid.generate_keys()

    # PÚBLICA: punto de la curva SIN COMPRIMIR (X9.62) = 1 byte 0x04 + X(32) +
    # Y(32) = 65 bytes. Es EL formato que pide `applicationServerKey`; el
    # comprimido (33 bytes) lo rechaza el navegador.
    publica = b64url(vapid.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    ))

    # SECRETA: el escalar privado crudo, 32 bytes big-endian. `pywebpush` la
    # reconoce por el largo (`Vapid.from_string`: 32 bytes → raw). Se elige
    # este formato y no PEM porque entra en UNA línea de JSON — un PEM tiene
    # saltos de línea y habría que escaparlos a mano en config.json.
    secreta = b64url(vapid.private_key.private_numbers().private_value.to_bytes(32, 'big'))

    return publica, secreta


def probar(publica, secreta, sub):
    """
    LA prueba: firma con la cadena SECRETA y verifica con la cadena PÚBLICA.
    Se parte de los strings, no de los objetos de arriba, porque lo que hay que
    probar es que lo que se va a pegar en config.json funciona.
    """
    # 1. Formato crudo, antes de criptografía: los largos que espera el navegador.
    crudo_pub = base64.urlsafe_b64decode(publica + '=' * (-len(publica) % 4))
    crudo_sec = base64.urlsafe_b64decode(secreta + '=' * (-len(secreta) % 4))
    _exigir(len(crudo_pub) == 65,
            f'la pública tiene {len(crudo_pub)} bytes, tienen que ser 65')
    _exigir(crudo_pub[0] == 0x04,
            'la pública no arranca con 0x04: no está sin comprimir')
    _exigir(len(crudo_sec) == 32,
            f'la secreta tiene {len(crudo_sec)} bytes, tienen que ser 32')

    # 2. Reconstruir desde el string, igual que hace pywebpush, y firmar.
    firmante = Vapid.from_string(private_key=secreta)
    try:
        cabeceras = firmante.sign({
            'sub': sub,
            'aud': AUD_PRUEBA,
            'exp': int(time.time()) + 60,
        })
    except VapidException as e:
        print(f'FALLÓ LA FIRMA DE PRUEBA: {e}')
        print(f'El `sub` tiene que ser un mailto: válido. Se probó con: {sub!r}')
        raise SystemExit(1)

    autorizacion = cabeceras['Authorization']

    # 3. La clave que el propio py_vapid publica en la cabecera (`k=`) tiene que
    #    ser IDÉNTICA a la que se va a guardar. Si no, el navegador se
    #    suscribiría con una clave y el servidor firmaría con otra.
    k = autorizacion.split('k=', 1)[1].split(',')[0]
    _exigir(k == publica, 'la cabecera firmada no lleva la misma clave pública')

    # 4. Y el cierre: verificar la firma con la PÚBLICA sola, que es lo único
    #    que tiene el servicio de push del otro lado.
    token = autorizacion.split('t=', 1)[1].split(',')[0]
    firmado, firma = token.rsplit('.', 1)
    verificador = Vapid.from_raw_public(publica.encode())
    _exigir(verificador.verify_token(firmado.encode(), firma), 'la firma no verifica')

    return autorizacion


def main():
    argv = sys.argv[1:]
    forzar = '--forzar' in argv
    sueltos = [a for a in argv if not a.startswith('--')]

    cfg = leer_config()
    abortar_si_ya_hay_claves(cfg, forzar)

    sub = (sueltos[0] if sueltos else (cfg.get('push_contacto_mailto') or '')).strip()
    sub_es_placeholder = not sub
    if sub_es_placeholder:
        sub = MAILTO_PRUEBA
    elif not sub.startswith('mailto:'):
        sub = 'mailto:' + sub

    publica, secreta = generar()
    autorizacion = probar(publica, secreta, sub)

    print(RAYA)
    print('PAR VAPID NUEVO — probado y funcionando')
    print(RAYA)
    print(f'Firma de prueba OK  ({len(autorizacion)} caracteres de Authorization,')
    print(f'firmada con la secreta y verificada con la pública, sub={sub})')
    print('')
    print('Pegar TAL CUAL en config.json (y después no tocar nunca más):')
    print('')
    print(f'  "push_vapid_publica":   "{publica}",')
    print(f'  "push_vapid_secreta":   "{secreta}",')
    if sub_es_placeholder:
        print('  "push_contacto_mailto": "mailto:PONER_UN_MAIL_DE_VERDAD@aca.com",')
    else:
        print(f'  "push_contacto_mailto": "{sub}",')
    print('')
    print('  (van con coma al final: config.json tiene 40 claves y esto se pega')
    print('   en el medio. Si lo pegás al final de todo, sacale la coma a la última.)')
    print('')
    print(f'  pública: {len(publica)} caracteres (65 bytes sin comprimir)')
    print(f'  secreta: {len(secreta)} caracteres (32 bytes)')
    if sub_es_placeholder:
        print('')
        print('⚠ El `sub` de arriba es un PLACEHOLDER: se usó solo para firmar la')
        print('  prueba. Apple valida ese mailto de verdad (es más estricto que')
        print('  FCM) — poner uno real antes de mandar el primer aviso.')
    print('')
    print(RAYA)
    print('ESTO NO SE VUELVE A CORRER.')
    print(RAYA)
    print('Un par nuevo invalida TODAS las suscripciones que existan, sin error')
    print('ni aviso: los avisos dejan de llegar y punto. Mismo trato que')
    print('`secret_key`. config.json está en .gitignore: la secreta no se')
    print('commitea, no se loguea y no se manda por chat.')


if __name__ == '__main__':
    main()
