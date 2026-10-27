import uuid

from smbprotocol.connection import Connection, Dialects
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect

from smbprotocol.open import (
    Open,
    CreateDisposition,
    FilePipePrinterAccessMask,
    FileAttributes,
    ShareAccess,
    CreateOptions,
    ImpersonationLevel
)

from smbprotocol.file_info import FileInformationClass


SERVER = "192.168.8.5"
SHARE = "Publica"

USERNAME = "sistemas"
PASSWORD = "Mapsa2020**"


def abrir_directorio(tree, ruta=""):

    directorio = Open(tree, ruta)

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



def listar_pdfs(tree, ruta=""):

    resultado = []

    try:

        directorio = abrir_directorio(tree, ruta)

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

                resultado.extend(
                    listar_pdfs(tree, ruta_actual)
                )


            else:

                if nombre.lower().endswith(".pdf"):

                    resultado.append(ruta_actual)


        directorio.close()


    except Exception as e:

        print(f"Error en {ruta}: {e}")


    return resultado



connection = None
session = None
tree = None


try:

    print("1. Conectando al servidor...")


    connection = Connection(
        uuid.uuid4(),
        SERVER,
        445
    )

    connection.connect(Dialects.SMB_3_0_0)

    print("2. Conexión SMB OK")


    session = Session(
        connection,
        USERNAME,
        PASSWORD,
        require_encryption=True
    )

    session.connect()

    print("3. Sesión autenticada OK")


    tree = TreeConnect(
        session,
        fr"\\{SERVER}\{SHARE}"
    )

    tree.connect()

    print("4. Share conectado OK")


    print("")
    print("Buscando PDFs...")
    print("----------------")


    pdfs = listar_pdfs(tree)


    for pdf in pdfs:
        print(pdf)


    print("")
    print("Total PDFs encontrados:", len(pdfs))


except Exception as e:

    print("")
    print("ERROR:")
    print(e)


finally:

    try:
        if tree:
            tree.disconnect()
    except:
        pass


    try:
        if session:
            session.disconnect()
    except:
        pass


    try:
        if connection:
            connection.disconnect()
    except:
        pass


    print("")
    print("Fin de prueba")