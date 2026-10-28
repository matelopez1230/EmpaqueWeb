# routes/especificaciones/envios_queue.py
"""
Banco de envíos con rate limiting (token bucket) y worker en background.
Persistente: al iniciar, re-encola los envíos huérfanos.
"""
import os
import queue
import threading
import time
import traceback

BURST       = int(os.environ.get("ENVIOS_BURST", "10"))
INTERVALO_S = float(os.environ.get("ENVIOS_INTERVALO_SEG", "2.0"))

_q = queue.Queue()
_worker_iniciado = False
_lock = threading.Lock()


class _TokenBucket:
    def __init__(self, capacity, interval):
        self.capacity = float(capacity)
        self.interval = float(interval)
        self.tokens = self.capacity
        self.last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self):
        while True:
            with self._lock:
                now = time.monotonic()
                delta = now - self.last
                self.last = now
                self.tokens = min(self.capacity, self.tokens + delta / self.interval)
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                falta = (1 - self.tokens) * self.interval
            time.sleep(min(falta, 0.5))


_bucket = _TokenBucket(BURST, INTERVALO_S)


def encolar(id_envio: int):
    _q.put(id_envio)


def _procesar(id_envio):
    """Procesa un envío. Los imports son locales para evitar ciclos."""
    from . import storage
    try:
        from .mailer import enviar_pdf, MailError
    except Exception as e:
        from . import storage as _s
        error_msg = f"Error importando mailer: {type(e).__name__} - {str(e)}"
        _s.marcar_envio_error(id_envio, error_msg)
        print(f"[envios_queue] {error_msg} (envío #{id_envio} falló)")
        return

    # `routes` todavía no existe en el paso 7 — pero este import solo se
    # ejecuta cuando llega un envío, no al importar el módulo
    try:
        from .routes import _pdf_de_publicado, _nombre_descarga_de
    except ImportError:
        storage.marcar_envio_error(id_envio, "routes.py no disponible todavía")
        print(f"[envios_queue] routes.py no está disponible, envío #{id_envio} falló")
        return

    envio = storage.obtener_envio(id_envio)
    if not envio or envio["estado"] != "pendiente":
        return

    storage.marcar_envio_enviando(id_envio)

    try:
        pdf_bytes, esp = _pdf_de_publicado(envio["id_esp"])
        if pdf_bytes is None or not esp:
            raise MailError("Error regenerando PDF (documento eliminado o inválido)")

        nombre = _nombre_descarga_de(esp)
        usuario = storage.obtener_usuario(envio["id_usuario"])

        enviar_pdf(
            destinatario=envio["destinatario"],
            pdf_bytes=pdf_bytes,
            nombre_archivo=nombre,
            asunto=envio["asunto"] or "Especificación",
            cuerpo=envio.get("cuerpo") or "Adjunto encontrará la especificación.",
            from_addr=envio["remitente"],
            from_name=(usuario or {}).get("nombre") or envio["remitente"],
            reply_to=(usuario or {}).get("email"),
        )

        storage.marcar_envio_enviado(id_envio)
        storage.registrar_contacto(envio["destinatario"])

    except Exception as e:
        err = str(e)[:500]
        storage.marcar_envio_error(id_envio, err)
        print(f"[envios_queue] Error en envío #{id_envio}: {err}")


def _worker():
    while True:
        id_envio = _q.get()
        try:
            _bucket.acquire()
            _procesar(id_envio)
        except Exception:
            traceback.print_exc()
        finally:
            _q.task_done()


def iniciar_worker():
    global _worker_iniciado
    with _lock:
        if _worker_iniciado:
            return
        _worker_iniciado = True

    try:
        from . import storage
        pendientes = storage.envios_pendientes()
        for e in pendientes:
            _q.put(e["id"])
        if pendientes:
            print(f"[envios_queue] {len(pendientes)} envíos huérfanos re-encolados")
    except Exception:
        traceback.print_exc()

    threading.Thread(target=_worker, name="envios-worker", daemon=True).start()
    print(f"[envios_queue] Worker iniciado (burst={BURST}, intervalo={INTERVALO_S}s)")