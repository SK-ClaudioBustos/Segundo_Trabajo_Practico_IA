# Segundo_Trabajo_Practico_IA

Repositorio del chat-bot necesario para realizar el TP 2 de IA

## Instrucciones de uso

1. Instalar Python 3.10

   Enlace de descarga [Python 3.10.11](https://www.python.org/downloads/release/python-31011/)

2. Crear un entorno virtual con python 3.10

   ```bash
      py -3.10 -m venv venv
   ```

3. Activar el entorno virtual cada vez que se use la terminal

   ```bash
      .\venv\Scripts\Activate.ps1
   ```

4. Navegar hasta dentro de la carpeta rasa

   ```bash
      cd ./rasa
   ```

5. Entrenamos el modelo, esto solo es necesario si se realizaron cambios en el modelo

   ```bash
      rasa train
   ```

6. Ejecutamos dos comandos, uno en cada terminal

   Terminal 1

   ```bash
      ..\venv\Scripts\python.exe -m rasa run actions
   ```

   Terminal 2

   ```bash
      ..\venv\Scripts\python.exe -m rasa shell
   ```
