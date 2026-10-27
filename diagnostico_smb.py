from smbprotocol.open import (
    FilePipePrinterAccessMask,
    FileAttributes,
    ShareAccess,
    CreateOptions,
    CreateDisposition,
    ImpersonationLevel
)

import inspect
from smbprotocol.open import Open


print("FIRMA CREATE:")
print(inspect.signature(Open.create))

print("\nFilePipePrinterAccessMask:")
print(dir(FilePipePrinterAccessMask))

print("\nFileAttributes:")
print(dir(FileAttributes))

print("\nShareAccess:")
print(dir(ShareAccess))

print("\nCreateOptions:")
print(dir(CreateOptions))

print("\nCreateDisposition:")
print(dir(CreateDisposition))

print("\nImpersonationLevel:")
print(dir(ImpersonationLevel))