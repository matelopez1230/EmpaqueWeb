from smb_client import SMBClient


smb = SMBClient()

try:

    smb.conectar()

    pdf = smb.leer_archivo("LOTES\\2026\\85529 SE115.pdf")

    print("PDF leído:", len(pdf.getvalue()), "bytes")


finally:

    smb.desconectar()