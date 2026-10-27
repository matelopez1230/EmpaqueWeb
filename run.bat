cd /d C:\EmpaqueWeb

echo INICIO >> C:\EmpaqueWeb\debug.txt
whoami >> C:\EmpaqueWeb\debug.txt
C:\EmpaqueWeb\env\Scripts\python.exe --version >> C:\EmpaqueWeb\debug.txt 2>&1

C:\EmpaqueWeb\env\Scripts\python.exe -m waitress --host=0.0.0.0 --port=8000 wsgi:app >> C:\EmpaqueWeb\debug.txt 2>&1