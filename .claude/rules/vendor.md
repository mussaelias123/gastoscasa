---
paths:
  - "static/vendor/**"
---

# `static/vendor/`: librerías de terceros con huella

- **NO editar a mano.** Cada archivo tiene huella SHA-256 en `HUELLAS` de `tests/test_vendor_integridad.py` → un byte distinto = test rojo.
- Versión nueva → carpeta NUEVA `static/vendor/<lib>-<versión>/` (+ LICENSE). Nunca pisar la vieja.
- Procedimiento completo: `docs/CONTEXT_SEGURIDAD.md` §"Actualizar una librería de terceros".
- `.gitattributes` (`static/vendor/** -text`) impide que git cambie fines de línea. No tocarlo.
