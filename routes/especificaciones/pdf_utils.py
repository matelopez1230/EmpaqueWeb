# routes/especificaciones/pdf_utils.py
import base64
import html
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from jinja2 import Environment, BaseLoader
import hashlib
import json as _json

# ─── Cache LRU en memoria (invalida al reiniciar Flask) ───
_CACHE       = {}
_CACHE_ORDER = []
_CACHE_MAX   = 50


def _cache_key(tipo, datos):
    s = _json.dumps({"tipo": tipo, "datos": datos},
                    sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _cache_get(k):
    if k in _CACHE:
        try:
            _CACHE_ORDER.remove(k)
        except ValueError:
            pass
        _CACHE_ORDER.append(k)
        return _CACHE[k]
    return None


def _cache_put(k, v):
    _CACHE[k] = v
    _CACHE_ORDER.append(k)
    while len(_CACHE_ORDER) > _CACHE_MAX:
        viejo = _CACHE_ORDER.pop(0)
        _CACHE.pop(viejo, None)


# ═══════════════════════════════════════════════════════════
# CAMBIO respecto a Empaque_v2: rutas apuntan a EmpaqueWeb/
# ═══════════════════════════════════════════════════════════
# __file__  = EmpaqueWeb/routes/especificaciones/pdf_utils.py
# .parent            = .../especificaciones/
# .parent.parent     = .../routes/
# .parent.parent.parent = EmpaqueWeb/
BASE_DIR       = Path(__file__).resolve().parent.parent.parent
PLANTILLAS_DIR = BASE_DIR / "plantillas" / "especificaciones"
UPLOADS_DIR    = BASE_DIR / "uploads" / "especificaciones"

LIBREOFFICE_PATHS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]

IMAGEN_ANCHO_MAX_CM = 18.0
IMAGEN_ALTO_MAX_CM  = 20.0

CAMPOS_IMAGEN = {
    "imagen_planteo_url":  "___IMG_PLANTEO_URL___",
    "imagen_planteo_ruta": "___IMG_PLANTEO_RUTA___",
    "imagen_plancha_url":  "___IMG_PLANCHA_URL___",
    "imagen_plancha_ruta": "___IMG_PLANCHA_RUTA___",
    "imagen":              "___IMG_ET___",
}


_env = Environment(
    loader=BaseLoader(),
    variable_start_string='{{',
    variable_end_string='}}',
    block_start_string='{%',
    block_end_string='%}',
    autoescape=False,
)


def _libreoffice_path() -> str:
    for p in LIBREOFFICE_PATHS:
        if os.path.isfile(p):
            return p
    raise RuntimeError("No se encontró LibreOffice.")


def _escape_odf(value) -> str:
    if value is None:
        return ''
    value = str(value)
    value = html.escape(value, quote=False)
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    value = value.replace('\n', '<text:line-break/>')
    return value


def _escape_rec(v):
    if isinstance(v, str):
        return _escape_odf(v)
    if isinstance(v, dict):
        return {k2: _escape_rec(v2) for k2, v2 in v.items()}
    if isinstance(v, list):
        return [_escape_rec(x) for x in v]
    return v


def verificar_imagen(url: str) -> tuple[bool, str]:
    if not url:
        return False, "URL vacía"
    try:
        with urlopen(url, timeout=5) as resp:
            content_type = resp.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                return False, f"No es imagen (Content-Type: {content_type})"
            return True, "Imagen válida"
    except Exception as e:
        return False, f"No accesible: {str(e)[:80]}"


def _dimensiones_imagen(data_bytes: bytes):
    try:
        from PIL import Image
        img = Image.open(BytesIO(data_bytes))
        return img.size
    except Exception:
        return None


def _leer_imagen_local(ruta_rel: str):
    if not ruta_rel:
        return None
    p = UPLOADS_DIR / ruta_rel
    if not p.exists() or not p.is_file():
        return None
    mimes = {
        '.png':  'image/png',
        '.jpg':  'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif':  'image/gif',
        '.webp': 'image/webp',
        '.bmp':  'image/bmp',
    }
    mime = mimes.get(p.suffix.lower(), 'image/png')
    return p.read_bytes(), mime


def _descargar_imagen_url(url: str):
    if not url:
        return None
    try:
        with urlopen(url, timeout=10) as resp:
            ct = resp.headers.get('Content-Type', 'image/png')
            return resp.read(), ct.split(';')[0].strip() or 'image/png'
    except Exception:
        return None


def _xml_frame_imagen(datos_bytes, mime='image/png', mensaje_error=''):
    if not datos_bytes:
        return f'<text:span>{html.escape(mensaje_error or "[Sin imagen]")}</text:span>'

    b64 = base64.b64encode(datos_bytes).decode('ascii')
    dims = _dimensiones_imagen(datos_bytes)
    if dims:
        w_px, h_px = dims
        ancho_cm = IMAGEN_ANCHO_MAX_CM
        alto_cm  = ancho_cm * h_px / w_px
        if alto_cm > IMAGEN_ALTO_MAX_CM:
            alto_cm  = IMAGEN_ALTO_MAX_CM
            ancho_cm = alto_cm * w_px / h_px
    else:
        ancho_cm = IMAGEN_ANCHO_MAX_CM
        alto_cm  = 10.0

    return (
        f'<draw:frame draw:style-name="fr1" draw:name="Imagen" '
        f'text:anchor-type="as-char" '
        f'svg:width="{ancho_cm:.2f}cm" svg:height="{alto_cm:.2f}cm" '
        f'draw:z-index="20">'
        f'<draw:image draw:mime-type="{mime}">'
        f'<office:binary-data>{b64}</office:binary-data>'
        f'</draw:image>'
        f'</draw:frame>'
    )


def _resolver_imagen(datos: dict, nombre_base: str):
    ruta = (
        datos.get(f"{nombre_base}_ruta")
        or datos.get(nombre_base)
        or ""
    ).strip()
    url  = (datos.get(f"{nombre_base}_url") or "").strip()

    if ruta:
        resultado = _leer_imagen_local(ruta)
        if resultado:
            return resultado[0], resultado[1], ""
        return None, 'image/png', f"[Archivo no encontrado: {ruta}]"

    if url:
        resultado = _descargar_imagen_url(url)
        if resultado:
            return resultado[0], resultado[1], ""
        return None, 'image/png', f"[URL no accesible: {url[:40]}]"

    return None, 'image/png', ""


def _insertar_campos_pagina(contenido: str) -> str:
    patron = re.compile(
        r'<text:span[^>]*>\s*P[áa]gina\s*\{\{\s*pagina_actual\s*\}\}\s*</text:span>',
        re.DOTALL | re.IGNORECASE,
    )
    reemplazo = (
        '<text:span text:style-name="T7">Página </text:span>'
        '<text:page-number text:select-page="current">1</text:page-number>'
        '<text:span text:style-name="T7"> de </text:span>'
        '<text:page-count>1</text:page-count>'
    )
    return patron.sub(reemplazo, contenido)


def generar_pdf(tipo: str, datos: dict) -> bytes:
    plantilla = PLANTILLAS_DIR / f"{tipo}.fodt"
    if not plantilla.exists():
        raise FileNotFoundError(f"Falta plantilla: {plantilla}")

    k = _cache_key(tipo, datos)
    cached = _cache_get(k)
    if cached is not None:
        print(f"⚡ cache hit ({tipo})")
        return cached
    datos.setdefault("incluir_anexo", False)
    datos.setdefault("versiones_anteriores", [])

    contenido = plantilla.read_text(encoding='utf-8')

    for campo, marcador in CAMPOS_IMAGEN.items():
        contenido = re.sub(
            r'\{\{\s*' + re.escape(campo) + r'\s*\}\}',
            marcador,
            contenido,
        )

    xml_por_marcador = {}
    for campo, marcador in CAMPOS_IMAGEN.items():
        base = campo.rsplit('_', 1)[0] if '_' in campo else campo
        img_bytes, img_mime, img_error = _resolver_imagen(datos, base)
        xml_por_marcador[marcador] = _xml_frame_imagen(img_bytes, img_mime, img_error)

    datos_esc = {k2: _escape_rec(v) for k2, v in datos.items()}

    template = _env.from_string(contenido)
    contenido_render = template.render(**datos_esc)

    for marcador, xml_frame in xml_por_marcador.items():
        contenido_render = contenido_render.replace(marcador, xml_frame)

    tmp_dir = Path(tempfile.gettempdir()) / f"espec_{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_fodt = tmp_dir / f"{tipo}.fodt"
    tmp_fodt.write_text(contenido_render, encoding='utf-8')

    perfil = tmp_dir / "lo_profile"
    perfil.mkdir(parents=True, exist_ok=True)

    cmd = [
        _libreoffice_path(),
        "--headless", "--norestore",
        f"-env:UserInstallation=file:///{perfil.as_posix()}",
        "--convert-to", "pdf",
        "--outdir", str(tmp_dir),
        str(tmp_fodt),
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=90)

    if resultado.returncode != 0:
        print(f"⚠️  LibreOffice falló. Temporal en: {tmp_dir}")
        print(f"    stderr: {resultado.stderr}")
        raise RuntimeError(f"LibreOffice falló:\n{resultado.stderr}")

    tmp_pdf = tmp_dir / f"{tipo}.pdf"
    if not tmp_pdf.exists():
        print(f"⚠️  No se generó PDF. Temporal en: {tmp_dir}")
        raise RuntimeError(f"LibreOffice no generó PDF:\n{resultado.stdout}")

    pdf_bytes = tmp_pdf.read_bytes()
    shutil.rmtree(tmp_dir, ignore_errors=True)
    _cache_put(k, pdf_bytes)
    return pdf_bytes