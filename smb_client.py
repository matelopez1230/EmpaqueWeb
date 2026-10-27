import uuid
import configparser
import os


from smbprotocol.connection import Connection, Dialects
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.exceptions import EndOfFile

from smbprotocol.open import (
    Open,
    CreateDisposition,
    FilePipePrinterAccessMask,
    ShareAccess,
    CreateOptions,
    ImpersonationLevel
)

from smbprotocol.file_info import FileInformationClass



class SMBClient:


    def __init__(self):

        self.connection = None
        self.session = None
        self.tree = None

        self.config = self.leer_config()



    def leer_config(self):

        archivo = os.path.join(
            os.path.dirname(__file__),
            "config_smb.ini"
        )

        config = configparser.ConfigParser()
        config.read(archivo)

        return {
            "host": config.get("SMB","host"),
            "share": config.get("SMB","share"),
            "username": config.get("SMB","username"),
            "password": config.get("SMB","password"),
            "path": config.get("SMB", "path", fallback="")
        }



    def conectar(self):

        self.connection = Connection(
            uuid.uuid4(),
            self.config["host"],
            445
        )

        self.connection.connect(
            Dialects.SMB_3_0_0
        )


        self.session = Session(
            self.connection,
            self.config["username"],
            self.config["password"],
            require_encryption=True
        )

        self.session.connect()


        self.tree = TreeConnect(
            self.session,
            fr"\\{self.config['host']}\{self.config['share']}"
        )

        self.tree.connect()

    def abrir_directorio(self, ruta=""):

        directorio = Open(
            self.tree,
            ruta
        )

        directorio.create(
            impersonation_level=ImpersonationLevel.Impersonation,
            desired_access=(
                FilePipePrinterAccessMask.GENERIC_READ |
                FilePipePrinterAccessMask.FILE_READ_ATTRIBUTES
            ),
            file_attributes=0,
            share_access=(
                ShareAccess.FILE_SHARE_READ |
                ShareAccess.FILE_SHARE_WRITE |
                ShareAccess.FILE_SHARE_DELETE
            ),
            create_disposition=CreateDisposition.FILE_OPEN,
            create_options=CreateOptions.FILE_DIRECTORY_FILE
        )

        return directorio
    
    def buscar_pdfs(self, ruta="", filtro=""):

        resultados = []

        try:

            directorio = self.abrir_directorio(ruta)

            archivos = directorio.query_directory(
                "*",
                FileInformationClass.FILE_DIRECTORY_INFORMATION
            )


            for archivo in archivos:

                nombre = archivo["file_name"].get_value()

                if not nombre:
                    continue

                nombre = nombre.decode("utf-16-le")


                if nombre in [".", ".."]:
                    continue


                ruta_actual = (
                    f"{ruta}\\{nombre}"
                    if ruta
                    else nombre
                )


                atributos = archivo["file_attributes"].get_value()


                # Es carpeta
                if atributos & 0x10:

                    resultados.extend(
                        self.buscar_pdfs(
                            ruta_actual,
                            filtro
                        )
                    )


                else:

                    if (
                        nombre.lower().endswith(".pdf")
                        and filtro.lower() in nombre.lower()
                    ):

                        resultados.append(
                            ruta_actual
                        )


            directorio.close()


        except Exception as e:

            print(f"Error buscando en {ruta}: {e}")


        return resultados
    
    
    def listar_todos_los_pdfs(self, ruta=""):

        resultados = []

        directorio = self.abrir_directorio(ruta)

        while True:

            try:

                archivos = directorio.query_directory(
                    "*",
                    FileInformationClass.FILE_DIRECTORY_INFORMATION
                )

            except Exception as e:

                # No hay más archivos
                if "STATUS_NO_MORE_FILES" in str(e):
                    break

                raise

            for archivo in archivos:

                nombre = archivo["file_name"].get_value()

                if not nombre:
                    continue

                nombre = nombre.decode("utf-16-le")

                if nombre in [".", ".."]:
                    continue

                atributos = archivo["file_attributes"].get_value()

                ruta_actual = (
                    f"{ruta}\\{nombre}"
                    if ruta
                    else nombre
                )

                # Es carpeta
                if atributos & 0x10:

                    resultados.extend(
                        self.listar_todos_los_pdfs(ruta_actual)
                    )

                else:

                    if nombre.lower().endswith(".pdf"):

                        resultados.append({
                            "nombre": nombre,
                            "ruta": ruta_actual
                        })

        directorio.close()

        return resultados
    
    def leer_archivo(self, ruta):

        from io import BytesIO

        archivo = Open(
            self.tree,
            ruta
        )

        archivo.create(
            impersonation_level=ImpersonationLevel.Impersonation,
            desired_access=(
                FilePipePrinterAccessMask.GENERIC_READ |
                FilePipePrinterAccessMask.FILE_READ_ATTRIBUTES
            ),
            file_attributes=0,
            share_access=(
                ShareAccess.FILE_SHARE_READ |
                ShareAccess.FILE_SHARE_WRITE |
                ShareAccess.FILE_SHARE_DELETE
            ),
            create_disposition=CreateDisposition.FILE_OPEN,
            create_options=0
        )


        datos = b""

        offset = 0
        bloque = 1024 * 1024   # 8 MB

        while True:

            try:

                parte = archivo.read(
                    length=bloque,
                    offset=offset
                )

                if not parte:
                    break

                datos += parte
                offset += len(parte)

            except EndOfFile:
                break
                

        archivo.close()


        return BytesIO(datos)



    def desconectar(self):

        if self.tree:
            self.tree.disconnect()

        if self.session:
            self.session.disconnect()

        if self.connection:
            self.connection.disconnect()