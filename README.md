# 📦 Módulo de Especificaciones (Integración en EmpaqueWeb)

Este documento detalla la arquitectura, los cambios estructurales y las configuraciones necesarias tras la integración exitosa del sistema de **Especificaciones** (anteriormente una app independiente en SQLite) dentro del sistema central **EmpaqueWeb**.

## 🏗️ 1. Arquitectura y Stack Tecnológico

El módulo ahora funciona como un **Blueprint** de Flask dentro de la aplicación principal, compartiendo la misma base de datos y sesión de usuario.

*   **Backend**: Python 3.12 / Flask 3.1
*   **Base de Datos**: Microsoft SQL Server (Migrado desde SQLite)
*   **Frontend**: Jinja2 + Bootstrap 4.5 + jQuery (Heredando el `base.html` global)
*   **Envío de Correos**: Microsoft Graph API (Reemplazando el uso de Outlook COM local)
*   **Generación de PDF**: WeasyPrint / LibreOffice headless (a partir de plantillas `.fodt`)

---

## 🗄️ 2. Base de Datos (SQL Server)

Toda la lógica de `especificaciones.db` fue migrada a la base de datos `GestionWeb`.

### Nuevas Tablas (`EspWeb*`)
*   `EspWebBorradores`: Documentos en edición.
*   `EspWebEspecificaciones`: Documentos publicados y versionados.
*   `EspWebPermisos`: Unificación de permisos globales y específicos (usa `IdBorrador NULL` para globales).
*   `EspWebEdicionActiva`: Control de bloqueo optimista (quién está editando).
*   `EspWebContactosCorreo`: Libreta de contactos para envíos.
*   `EspWebEnviosCorreo`: Historial y cola de envíos.
*   `EspWebNotificaciones`: Alertas de cambios y publicaciones.

### Modificaciones a Tablas Existentes
*   **`EmpWebUsuarios`**: Se agregaron las columnas `Nombre` y `Apellido`. Se utiliza el campo `Email` para el remitente de Graph API.
*   **`EmpWebMenus`**: Se creó el grupo `ESPECIFICACIONES` con los accesos directos a: Diseño Gráfico, Material de Empaque, Etiquetas, Etiquetas Zebra, Contactos y Panel.

### Fixes Críticos de SQL Server (pyodbc)
*   **Reemplazo de `SCOPE_IDENTITY()`**: Se cambió por `OUTPUT INSERTED.IdXxx` en todos los `INSERT`, ya que pyodbc devolvía `None`.
*   **Normalización de Fechas**: La función `_normalizar_valor()` en `storage.py` convierte los objetos `datetime` de SQL Server a strings para evitar el error `not subscriptable` en los templates al usar filtros como `[:10]`.

---

## ⚙️ 3. Backend (Flask)

*   **Blueprint `especificaciones`**: Registrado en `app.py` bajo el prefijo `/especificaciones`.
*   **Worker en Segundo Plano**: En `app.py` se inicializa `iniciar_worker()` (de `envios_queue.py`) para procesar la cola de correos sin bloquear la app principal.
*   **`mailer.py`**: Reescrito para usar `msal` y `requests` (Microsoft Graph API). Incluye lógica de *fallback* (si el usuario no tiene buzón propio, envía desde una cuenta de notificaciones pero mantiene su nombre y email de respuesta).
*   **Comportamientos por Tipo**: Las rutas ahora incluyen el tipo en la URL (ej. `/especificaciones/tipo/diseno_grafico`), mapeando automáticamente al archivo `.fodt` correcto.

---

## 🎨 4. Frontend (Templates)

*   **Navbar Dinámico**: El menú "Especificaciones" se construye dinámicamente consultando `EmpWebMenus` y `EmpWebPermisosUsuario`.
*   **`templates/especificaciones/`**: Todos los HTML de `empaque_v2` fueron migrados y adaptados para heredar (`{% extends %}`) del `base.html` de EmpaqueWeb.
*   **Página de Contactos (`/especificaciones/contactos`)**: Nueva interfaz (CRUD completo) con modales para agregar/editar nombre y correo de los contactos.
*   **Página de Usuarios (`templates/usuarios/index.html`)**: Actualizada para permitir gestionar el Nombre, Apellido y Email de cada operador del sistema.
*   **Visor de PDFs**: Se eliminó el botón legacy de "Abrir Outlook" (tanto en el HTML como en las rutas del backend), ya que el envío ahora se maneja 100% por API.

---

## ☁️ 5. Configuración de Microsoft Entra ID (Graph API)

Para que el envío de correos funcione, es obligatorio configurar una App en Azure/Entra ID con el permiso de aplicación `Mail.Send` y el consentimiento de administrador otorgado.

### Variables de Entorno (`.env`)
Crear un archivo `.env` en la raíz del proyecto con las siguientes credenciales:

```env
GRAPH_TENANT_ID=tu-tenant-id-de-entra
GRAPH_CLIENT_ID=tu-client-id-de-la-app
GRAPH_CLIENT_SECRET=tu-secreto-de-cliente
GRAPH_REMITENTE=notificaciones@tudominio.com
DRY_RUN=0
