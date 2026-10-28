# routes/especificaciones/mailer.py
"""
Envío de correos usando Microsoft Graph API (Client Credentials flow).

Requiere variables de entorno:
    GRAPH_TENANT_ID     : ID del tenant de Entra ID
    GRAPH_CLIENT_ID     : ID de la aplicación registrada
    GRAPH_CLIENT_SECRET : Secreto del cliente
    GRAPH_REMITENTE     : Email del remitente por defecto

Mantiene la misma API que el mailer.py viejo (Outlook COM):
    enviar_pdf(destinatario, pdf_bytes, nombre_archivo, asunto, cuerpo,
               from_addr=None, from_name=None, reply_to=None)
"""
import os
import base64
import html as _html

import msal
import requests


class MailError(Exception):
    pass


# ═══════════════════════════════════════════════════════════
# Configuración
# ═══════════════════════════════════════════════════════════

TENANT_ID     = os.environ.get("GRAPH_TENANT_ID", "").strip()
CLIENT_ID     = os.environ.get("GRAPH_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET", "").strip()
REMITENTE     = os.environ.get("GRAPH_REMITENTE", "").strip().lower()
DRY_RUN       = os.environ.get("DRY_RUN", "0") == "1"

GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"
AUTHORITY      = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES         = ["https://graph.microsoft.com/.default"]

# Límite de Graph para adjuntos en envíos simples
MAX_ATTACHMENT_MB = 3


# ═══════════════════════════════════════════════════════════
# Autenticación (con cache automático de tokens)
# ═══════════════════════════════════════════════════════════

_msal_app = None


def _validar_config():
    faltantes = []
    if not TENANT_ID:     faltantes.append("GRAPH_TENANT_ID")
    if not CLIENT_ID:     faltantes.append("GRAPH_CLIENT_ID")
    if not CLIENT_SECRET: faltantes.append("GRAPH_CLIENT_SECRET")
    if faltantes:
        raise MailError(
            f"Faltan variables de entorno: {', '.join(faltantes)}. "
            f"Configuralas en .env o en las variables de entorno del sistema."
        )


def _get_msal_app():
    global _msal_app
    if _msal_app is None:
        _validar_config()
        _msal_app = msal.ConfidentialClientApplication(
            CLIENT_ID,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET,
        )
    return _msal_app


def _get_token():
    """Obtiene (o reutiliza del cache) un access token para Graph."""
    app = _get_msal_app()
    result = app.acquire_token_for_client(scopes=SCOPES)
    if "access_token" not in result:
        error = result.get("error_description") or result.get("error", "unknown")
        raise MailError(f"No se pudo obtener token de Graph: {error}")
    return result["access_token"]


# ═══════════════════════════════════════════════════════════
# Envío
# ═══════════════════════════════════════════════════════════

def enviar_pdf(destinatario, pdf_bytes, nombre_archivo, asunto, cuerpo,
               from_addr=None, from_name=None, reply_to=None):
    """
    Envía un correo con PDF adjunto usando Microsoft Graph API.

    Estrategia de remitente:
      1. Intenta enviar DESDE el buzón del usuario (from_addr).
      2. Si el buzón no existe en el tenant (404), reintenta DESDE
         el buzón de notificaciones (REMITENTE del .env), pero
         mostrando el nombre del usuario y su email como reply-to.
    """
    if not destinatario or "@" not in destinatario:
        raise MailError("Destinatario inválido")

    if DRY_RUN:
        print(f"[DRY-RUN] Graph → Para: {destinatario} | Adjunto: {nombre_archivo}")
        return True

    _validar_config()

    sender_usuario = (from_addr or "").strip().lower()
    sender_fallback = REMITENTE

    # Validar tamaño
    tamaño_mb = len(pdf_bytes) / (1024 * 1024)
    if tamaño_mb > MAX_ATTACHMENT_MB:
        raise MailError(
            f"PDF demasiado grande ({tamaño_mb:.1f} MB). "
            f"Graph API acepta máximo {MAX_ATTACHMENT_MB} MB por adjunto."
        )

    cuerpo_esc = _html.escape(
        cuerpo or "Adjunto encontrará la especificación solicitada."
    )
    cuerpo_html = cuerpo_esc.replace("\n", "<br>")

    def _armar_mensaje(sender, reply, nombre_visible):
        msg = {
            "message": {
                "subject": asunto or "Especificación",
                "body": {
                    "contentType": "HTML",
                    "content": cuerpo_html,
                },
                "toRecipients": [
                    {"emailAddress": {"address": destinatario}}
                ],
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": nombre_archivo or "especificacion.pdf",
                        "contentType": "application/pdf",
                        "contentBytes": base64.b64encode(pdf_bytes).decode("ascii"),
                    }
                ],
            },
            "saveToSentItems": True,
        }
        if reply:
            msg["message"]["replyTo"] = [
                {"emailAddress": {"address": reply}}
            ]
        if nombre_visible and sender == sender_fallback:
            # Solo ponemos "from" con nombre cuando usamos el fallback
            # (si usamos el buzón del usuario, Graph ya usa el nombre del buzón)
            msg["message"]["from"] = {
                "emailAddress": {
                    "address": sender,
                    "name": nombre_visible,
                }
            }
        return msg

    def _enviar(sender, mensaje):
        token = _get_token()
        url = f"{GRAPH_ENDPOINT}/users/{sender}/sendMail"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        return requests.post(url, headers=headers, json=mensaje, timeout=30)

    # ═══ Intento 1: desde el buzón del usuario ═══
    error_1 = None
    if sender_usuario and "@" in sender_usuario:
        mensaje = _armar_mensaje(sender_usuario, reply_to or sender_usuario, from_name)
        try:
            resp = _enviar(sender_usuario, mensaje)
            if resp.status_code == 202:
                print(f"[mailer] Enviado desde buzón del usuario: {sender_usuario}")
                return True
            # 404 = buzón no existe en el tenant → caemos al fallback
            if resp.status_code in (404, 400):
                error_1 = f"{resp.status_code}: {resp.text[:200]}"
                print(f"[mailer] Buzón {sender_usuario} no válido → fallback a {sender_fallback}")
            else:
                # 401/403 u otro → error definitivo (no tiene sentido reintentar)
                try:
                    err = resp.json().get("error", {}).get("message", resp.text[:300])
                except Exception:
                    err = resp.text[:300]
                raise MailError(f"Graph API devolvió {resp.status_code}: {err}")
        except requests.RequestException as e:
            raise MailError(f"Error de red al llamar a Graph: {str(e)[:200]}")

    # ═══ Intento 2: fallback al buzón de notificaciones ═══
    if not sender_fallback or "@" not in sender_fallback:
        raise MailError(
            f"El buzón del usuario '{sender_usuario}' no es válido "
            f"y no hay GRAPH_REMITENTE configurado como fallback. "
            f"Error original: {error_1 or 'desconocido'}"
        )

    nombre_visible = from_name or sender_usuario or "EmpaqueWeb"
    mensaje = _armar_mensaje(sender_fallback, sender_usuario, nombre_visible)
    try:
        resp = _enviar(sender_fallback, mensaje)
    except requests.RequestException as e:
        raise MailError(f"Error de red al llamar a Graph (fallback): {str(e)[:200]}")

    if resp.status_code == 202:
        print(f"[mailer] Enviado desde fallback {sender_fallback} "
              f"(from_name={nombre_visible}, reply_to={sender_usuario})")
        return True

    try:
        err = resp.json().get("error", {}).get("message", resp.text[:300])
    except Exception:
        err = resp.text[:300]
    raise MailError(f"Graph API (fallback) devolvió {resp.status_code}: {err}")