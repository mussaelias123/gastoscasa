"""Validador de estilo telegráfico (METODOLOGIA §2b). Sin LLM, solo stdlib.
Lo corre el sub-agente `compactador`; sirve también a mano.

  python TempScripts/validar_telegrafico.py respaldar ARCHIVO     → copia del original fuera del repo
  python TempScripts/validar_telegrafico.py validar ARCHIVO       → compara contra esa copia
  python TempScripts/validar_telegrafico.py validar ORIGINAL NUEVO
  python TempScripts/validar_telegrafico.py restaurar ARCHIVO     → vuelve al original

Salida: OK (exit 0) · RECHAZADO (1: falta texto crítico) · sin respaldo (2) · CODIGO CAMBIADO (3: restaurar).
Chequea: spans `código`, rutas, número+unidad, números, total de negaciones, ⚠, títulos, filas de tabla, bloques ```.
Código (.py .js .css .html): además, código idéntico. .py → AST + tokens; resto → líneas que no son comentario.
"""
import ast
import hashlib
import io
import re
import shutil
import sys
import tempfile
import tokenize
from collections import Counter
from pathlib import Path

CODIGO = {".py", ".js", ".css", ".html"}
RE_CODE = re.compile(r"`[^`\n]+`")
RE_PATH = re.compile(r"[\w./\\-]*\w\.(?:py|md|js|html|css|json|db|txt|png|exe|log|yml|yaml|ini|sh|ps1|zst)\b")
RE_NUM = re.compile(r"\d[\d.,:/]*\d|\d")
RE_UNIT = re.compile(r"(\d[\d.,]*)\s?(días|día|horas?|h|minutos?|min|segundos?|s|ms|MB|GB|KB|k|%|tokens|líneas|bytes|meses)\b")
RE_NEG = re.compile(r"(?i)\b(no|nunca|ni|sin|jamás|tampoco|ningún|ninguna|ninguno|solo|sólo|siempre)\b")
RE_HEAD = re.compile(r"(?m)^\s*(#{1,6} .+?)\s*$")
RE_TROW = re.compile(r"(?m)^\s*\|")
RE_FENCE = re.compile(r"```.*?```", re.S)


def respaldo(ruta):
    """Copia en %TEMP%/compactador, nombre por hash de la ruta: nada queda dentro del repo."""
    p = Path(ruta).resolve()
    h = hashlib.sha1(str(p).lower().encode()).hexdigest()[:10]
    d = Path(tempfile.gettempdir()) / "compactador"
    d.mkdir(exist_ok=True)
    return d / f"{h}_{p.name}"


def leer(p):
    return Path(p).read_text(encoding="utf-8").replace("\r\n", "\n")


def faltantes(items, texto):
    return [f"{it} (x{n - texto.count(it)})" for it, n in Counter(items).items() if texto.count(it) < n]


def firma_py(t):
    """AST con docstrings normalizados (se pueden reescribir) + tokens sin comentarios ni strings."""
    arbol = ast.parse(t)
    for nodo in ast.walk(arbol):
        cuerpo = getattr(nodo, "body", None)
        if isinstance(cuerpo, list) and cuerpo and isinstance(cuerpo[0], ast.Expr) \
                and isinstance(getattr(cuerpo[0], "value", None), ast.Constant) and isinstance(cuerpo[0].value.value, str):
            cuerpo[0].value.value = "<doc>"
    fuera = (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.STRING)
    toks = [(x.type, x.string) for x in tokenize.generate_tokens(io.StringIO(t).readline) if x.type not in fuera]
    return ast.dump(arbol), toks  # strings que no son docstring (SQL, etc.) quedan en el AST


def lineas_codigo(t):
    """Líneas que NO son comentario completo (// /* */ {# #} <!-- -->).
    Comentario al final de una línea de código = parte del código: no se toca."""
    out, cierre = [], None
    for ln in t.split("\n"):
        s = ln.strip()
        if cierre:
            if cierre in s:
                resto = s.split(cierre, 1)[1].strip()
                cierre = None
                if resto:
                    out.append(resto)
            continue
        if not s or s.startswith("//"):
            continue
        for a, c in (("/*", "*/"), ("<!--", "-->"), ("{#", "#}")):
            if s.startswith(a):
                if c in s[len(a):]:
                    resto = s[len(a):].split(c, 1)[1].strip()
                    if resto:
                        out.append(resto)
                else:
                    cierre = c
                break
        else:
            out.append(s)
    return out


def validar(o, c, ext):
    if ext in CODIGO:
        try:
            igual = firma_py(o) == firma_py(c) if ext == ".py" else lineas_codigo(o) == lineas_codigo(c)
        except SyntaxError:
            igual = False
        if not igual:
            return {"CODIGO CAMBIADO": ["el código no es idéntico: correr 'restaurar'"]}
    prob = {
        "código": faltantes(RE_CODE.findall(o), c),
        "rutas": faltantes(RE_PATH.findall(o), c),
        "número+unidad": [f"{n} {u}" for n, u in set(RE_UNIT.findall(o))
                          if not re.search(re.escape(n) + r"\s?" + re.escape(u), c)],
    }
    no, nc = Counter(RE_NUM.findall(o)), Counter(RE_NUM.findall(c))
    prob["números"] = [f"{k} (x{v - nc[k]})" for k, v in no.items() if nc[k] < v]
    go = Counter(m.lower() for m in RE_NEG.findall(o))
    gc = Counter(m.lower() for m in RE_NEG.findall(c))
    if sum(gc.values()) < sum(go.values()):  # "no hay" → "sin" mantiene la negación; perderla baja el total
        prob["negaciones"] = [f"total {sum(gc.values())}/{sum(go.values())}"] + \
                             [f"{k}: {gc[k]}/{v}" for k, v in go.items() if gc[k] < v]
    if c.count("⚠") < o.count("⚠"):
        prob["⚠"] = [f"{c.count('⚠')}/{o.count('⚠')}"]
    if ext not in CODIGO:  # en código '# ...' es comentario, no título
        hc = {h.strip() for h in RE_HEAD.findall(c)}
        prob["títulos"] = [h for h in RE_HEAD.findall(o) if h.strip() not in hc]
        if len(RE_TROW.findall(c)) < len(RE_TROW.findall(o)):
            prob["filas de tabla"] = [f"{len(RE_TROW.findall(c))}/{len(RE_TROW.findall(o))}"]
    prob["bloques ```"] = [b[:40] + "…" for b in RE_FENCE.findall(o) if b not in c]
    return {k: v for k, v in prob.items() if v}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # consola Windows: ⚠ y … rompen cp1252
    if len(argv) < 2 or argv[0] not in ("respaldar", "validar", "restaurar"):
        print(__doc__)
        return 2
    cmd, ruta = argv[0], argv[1]
    if cmd == "respaldar":
        shutil.copyfile(ruta, respaldo(ruta))
        print(f"respaldo: {respaldo(ruta)}")
        return 0
    if cmd == "restaurar":
        if not respaldo(ruta).exists():
            print("sin respaldo")
            return 2
        shutil.copyfile(respaldo(ruta), ruta)
        print(f"restaurado: {ruta}")
        return 0
    if len(argv) >= 3:
        o, c, ext = leer(argv[1]), leer(argv[2]), Path(argv[2]).suffix.lower()
    else:
        if not respaldo(ruta).exists():
            print("sin respaldo: correr 'respaldar' ANTES de reescribir")
            return 2
        o, c, ext = leer(respaldo(ruta)), leer(ruta), Path(ruta).suffix.lower()
    prob = validar(o, c, ext)
    print(f"tamaño: {len(c) / max(1, len(o)):.0%} de los caracteres")
    for k, v in prob.items():
        print(f"FALTA {k}: " + "; ".join(v[:15]) + (" …" if len(v) > 15 else ""))
    if "CODIGO CAMBIADO" in prob:
        print("CODIGO CAMBIADO")
        return 3
    print("OK" if not prob else "RECHAZADO")
    return 0 if not prob else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
