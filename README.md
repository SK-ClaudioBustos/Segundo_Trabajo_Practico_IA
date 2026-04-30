# Segundo_Trabajo_Practico_IA

Repositorio del chat-bot necesario para realizar el TP 2 de IA

## Instrucciones de uso

1. Instalar Python 3.10

   Enlace de descarga [Python 3.10.11](https://www.python.org/downloads/release/python-31011/)

2. Crear un entorno virtual con python 3.10

   ```powershell
      py -3.10 -m venv venv
   ```

3. Activar el entorno virtual cada vez que se use la terminal

   ```powershell
      .\venv\Scripts\Activate.ps1
   ```

4. Instalar dependencias del proyecto

   ```powershell
      pip install -r requirements.txt
   ```

5. Navegar hasta dentro de la carpeta rasa

   ```powershell
      cd ./rasa
   ```

6. Entrenamos el modelo. Esto es necesario la primera vez y cada vez que se realicen cambios en el modelo

   ```powershell
      rasa train
   ```

7. Ejecutamos dos comandos, uno en cada terminal. En cada terminal nueva, hay que activar el entorno virtual y navegar a la carpeta rasa

   Terminal 1

   ```powershell
      .\venv\Scripts\Activate.ps1
      cd ./rasa
      rasa run actions
   ```

   Terminal 2

   ```powershell
      .\venv\Scripts\Activate.ps1
      cd ./rasa
      rasa shell
   ```
