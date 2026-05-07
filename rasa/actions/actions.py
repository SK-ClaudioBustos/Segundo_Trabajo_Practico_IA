import re
import os
import yaml
from thefuzz import process, fuzz
from typing import Any, Text, Dict, List

import requests
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, ConversationPaused,  SessionStarted, ActionExecuted

# =============================================================================
# Utilidades
# =============================================================================

TIPOS_ES_EN = {
    "normal": "normal", "fuego": "fire", "agua": "water", "planta": "grass",
    "eléctrico": "electric", "electrico": "electric", "hielo": "ice",
    "lucha": "fighting", "veneno": "poison", "tierra": "ground",
    "volador": "flying", "psíquico": "psychic", "psiquico": "psychic",
    "bicho": "bug", "roca": "rock", "fantasma": "ghost",
    "dragón": "dragon", "dragon": "dragon", "siniestro": "dark",
    "acero": "steel", "hada": "fairy",
}

TIPOS_EN_ES = {
    "normal": "Normal", "fire": "Fuego", "water": "Agua", "grass": "Planta",
    "electric": "Eléctrico", "ice": "Hielo", "fighting": "Lucha",
    "poison": "Veneno", "ground": "Tierra", "flying": "Volador",
    "psychic": "Psíquico", "bug": "Bicho", "rock": "Roca",
    "ghost": "Fantasma", "dragon": "Dragón", "dark": "Siniestro",
    "steel": "Acero", "fairy": "Hada",
}

STATS_EN_ES = {
    "hp": "HP (Puntos de vida)", "attack": "Ataque", "defense": "Defensa",
    "special-attack": "Ataque Especial", "special-defense": "Defensa Especial",
    "speed": "Velocidad",
}

# Mapeo de generaciones: texto en español -> ID de la PokeAPI
GENERACIONES_MAP = {
    "primera": 1, "1": 1, "i": 1,
    "segunda": 2, "2": 2, "ii": 2,
    "tercera": 3, "3": 3, "iii": 3,
    "cuarta": 4, "4": 4, "iv": 4,
    "quinta": 5, "5": 5, "v": 5,
    "sexta": 6, "6": 6, "vi": 6,
    "septima": 7, "7": 7, "vii": 7,
    "octava": 8, "8": 8, "viii": 8,
    "novena": 9, "9": 9, "ix": 9,
    "decima": 10, "10": 10, "x": 10,
}

GENERACION_NOMBRES = {
    1: "Primera (Kanto)", 2: "Segunda (Johto)", 3: "Tercera (Hoenn)",
    4: "Cuarta (Sinnoh)", 5: "Quinta (Unova/Teselia)", 6: "Sexta (Kalos)",
    7: "Septima (Alola)", 8: "Octava (Galar)", 9: "Novena (Paldea)",
    10: "Decima (Desconocida)",
}

POKEAPI_BASE_URL = "https://pokeapi.co/api/v2"

# Cache para nombres de pokemon
POKEMON_NAMES_CACHE = []


def cargar_nombres_pokemon():
    """Carga los nombres de pokemon desde la lookup table en nlu.yml."""
    global POKEMON_NAMES_CACHE
    if POKEMON_NAMES_CACHE:
        return POKEMON_NAMES_CACHE

    # Construir ruta relativa a data/nlu.yml
    path_actual = os.path.dirname(__file__)
    nlu_path = os.path.abspath(os.path.join(path_actual, "..", "data", "nlu.yml"))

    try:
        with open(nlu_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            for item in data.get('nlu', []):
                if 'lookup' in item and item['lookup'] == 'nombre_pokemon':
                    examples = item.get('examples', "").split('\n')
                    # Limpiar y filtrar nombres
                    POKEMON_NAMES_CACHE = [
                        e.strip('- ').lower()
                        for e in examples
                        if e.strip('- ')
                    ]
                    break
    except Exception as e:
        print(f"Error al cargar nombres de pokemon: {e}")

    return POKEMON_NAMES_CACHE


def corregir_nombre_pokemon(nombre_usuario: str) -> str:
    """Busca el nombre de pokemon mas parecido usando fuzzy matching."""
    if not nombre_usuario:
        return ""

    nombres_validos = cargar_nombres_pokemon()
    if not nombres_validos:
        return nombre_usuario

    nombre_query = nombre_usuario.lower().strip()

    # 1. Intento match exacto (despues de sanitizar)
    if nombre_query in nombres_validos:
        return nombre_query

    # 2. Fuzzy matching
    # Usamos QRatio que es mejor para comparar palabras sueltas
    best_match, score = process.extractOne(nombre_query, nombres_validos, scorer=fuzz.QRatio)

    # Si la confianza es aceptable (>= 75), asumimos que es ese pokemon
    if score >= 75:
        return best_match

    # Si no estamos seguros, devolvemos el original
    return nombre_query


def sugerir_nombre_pokemon(nombre_usuario: str) -> str:
    """Busca una sugerencia si el match no fue lo suficientemente fuerte para auto-corregir."""
    if not nombre_usuario:
        return ""

    nombres_validos = cargar_nombres_pokemon()
    if not nombres_validos:
        return ""

    best_match, score = process.extractOne(nombre_usuario, nombres_validos, scorer=fuzz.QRatio)

    # Si tiene una confianza decente (>= 60) pero no fue auto-corregido (< 75)
    if 60 <= score < 75:
        return best_match

    return ""


def sanitizar_entrada(texto: str) -> str:
    """Sanitiza la entrada del usuario."""
    if not texto:
        return ""
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-záéíóúñü0-9\s\-]", "", texto)
    return texto.strip()


def traducir_tipo_a_ingles(tipo_es: str) -> str:
    tipo_limpio = sanitizar_entrada(tipo_es)
    return TIPOS_ES_EN.get(tipo_limpio, tipo_limpio)


def traducir_tipo_a_espanol(tipo_en: str) -> str:
    return TIPOS_EN_ES.get(tipo_en.lower(), tipo_en.capitalize())


def obtener_nombre_pokemon(tracker: Tracker) -> str:
    nombre = next(tracker.get_latest_entity_values("nombre_pokemon"), None)
    if not nombre:
        nombre = tracker.get_slot("nombre_pokemon")
    if not nombre:
        return ""

    # Aplicamos sanitizacion basica y luego correccion fuzzy
    nombre_sanitizado = sanitizar_entrada(nombre)
    nombre_corregido = corregir_nombre_pokemon(nombre_sanitizado)

    return nombre_corregido


def consultar_pokeapi(nombre: str) -> dict:
    response = requests.get(f"{POKEAPI_BASE_URL}/pokemon/{nombre}", timeout=10)
    if response.status_code == 200:
        return response.json()
    return None


def manejar_error_pokemon(dispatcher, nombre, error_tipo="no_encontrado"):
    if error_tipo == "no_encontrado":
        sugerencia = sugerir_nombre_pokemon(nombre)
        if sugerencia:
            dispatcher.utter_message(
                text=f"No encontre ningun Pokemon llamado '{nombre}'. ¿Quisiste decir '{sugerencia.capitalize()}'?"
            )
            return

    mensajes = {
        "no_encontrado": f"No encontre ningun Pokemon llamado '{nombre}'. Asegurate de escribir bien el nombre.",
        "sin_nombre": "No mencionaste ningun Pokemon y no tengo uno en memoria. Primero consulta un Pokemon, por ejemplo: 'Contame sobre Pikachu'",
        "nombre_invalido": "El nombre que ingresaste no es valido. Proba con un nombre como 'Pikachu' o 'Charizard'.",
        "api_error": "Hubo un problema al consultar la PokeAPI. Intenta de nuevo en unos segundos.",
        "timeout": "La PokeAPI tardo mucho en responder. Intenta de nuevo en un momento.",
        "conexion": "No pude conectarme a la PokeAPI. Verifica tu conexion a internet.",
        "inesperado": "Ocurrio un error inesperado. Intenta de nuevo.",
    }
    dispatcher.utter_message(text=mensajes.get(error_tipo, mensajes["inesperado"]))


def ejecutar_con_manejo_errores(dispatcher, nombre, funcion_principal):
    """Wrapper para manejar errores de API en todas las actions."""
    try:
        return funcion_principal()
    except requests.exceptions.Timeout:
        manejar_error_pokemon(dispatcher, nombre, "timeout")
    except requests.exceptions.ConnectionError:
        manejar_error_pokemon(dispatcher, nombre, "conexion")
    except Exception:
        manejar_error_pokemon(dispatcher, nombre, "inesperado")
    return []


# =============================================================================
# Funciones de consulta reutilizables (usadas por actions y por contexto)
# =============================================================================

def _hacer_consulta_pokemon(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    pokemon_id = data["id"]
    tipos = ", ".join(traducir_tipo_a_espanol(t["type"]["name"]) for t in data["types"])
    peso = data["weight"] / 10
    altura = data["height"] / 10
    habilidades = ", ".join(h["ability"]["name"].replace("-", " ").capitalize() for h in data["abilities"])
    stats = "\n".join(f"  - {s['stat']['name'].replace('-', ' ').upper()}: {s['base_stat']}" for s in data["stats"])
    mensaje = (
        f"** {pokemon_nombre} ** (#{pokemon_id})\n\n"
        f"Tipo(s): {tipos}\nPeso: {peso} kg\nAltura: {altura} m\n"
        f"Habilidades: {habilidades}\n\nEstadisticas base:\n{stats}\n\n"
        f"Podes preguntarme datos especificos como: 'cuanto pesa?', 'cuanto ataque tiene?', 'de que tipo es?'"
    )
    dispatcher.utter_message(text=mensaje)
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "pokemon")]


def _hacer_consulta_peso(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    peso_kg = data["weight"] / 10
    peso_lb = round(peso_kg * 2.20462, 1)
    dispatcher.utter_message(text=f"{pokemon_nombre} pesa {peso_kg} kg (aprox. {peso_lb} lbs)")
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "peso")]


def _hacer_consulta_altura(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    altura_m = data["height"] / 10
    altura_ft = round(altura_m * 3.28084, 1)
    dispatcher.utter_message(text=f"{pokemon_nombre} mide {altura_m} m (aprox. {altura_ft} pies)")
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "altura")]


def _hacer_consulta_estadistica(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    stats_info = []
    total_stats = 0
    for s in data["stats"]:
        stat_nombre = STATS_EN_ES.get(s["stat"]["name"], s["stat"]["name"].replace("-", " ").capitalize())
        valor = s["base_stat"]
        total_stats += valor
        barra_len = int(valor / 255 * 20)
        barra = "#" * barra_len + "-" * (20 - barra_len)
        stats_info.append(f"  {stat_nombre}: {valor} [{barra}]")
    stats_text = "\n".join(stats_info)
    dispatcher.utter_message(text=f"Estadisticas base de {pokemon_nombre}:\n\n{stats_text}\n\nTotal: {total_stats}")
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "estadistica")]


def _hacer_consulta_habilidad(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    habilidades_info = []
    for h in data["abilities"]:
        nombre_hab = h["ability"]["name"].replace("-", " ").capitalize()
        es_oculta = " (oculta)" if h["is_hidden"] else ""
        habilidades_info.append(f"  - {nombre_hab}{es_oculta}")
    lista_habilidades = "\n".join(habilidades_info)
    dispatcher.utter_message(text=f"Habilidades de {pokemon_nombre}:\n\n{lista_habilidades}")
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "habilidad")]


def _hacer_consulta_tipo_pokemon(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    tipos = ", ".join(traducir_tipo_a_espanol(t["type"]["name"]) for t in data["types"])
    dispatcher.utter_message(text=f"{pokemon_nombre} es de tipo {tipos}.")
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "tipo_pokemon")]


def _hacer_consulta_id_pokemon(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    pokemon_id = data["id"]
    dispatcher.utter_message(text=f"El numero de {pokemon_nombre} en la Pokedex es #{pokemon_id}.")
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "id_pokemon")]


def _hacer_consulta_generacion_pokemon(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    
    pokemon_nombre = data["name"].capitalize()
    generacion = "Desconocida"
    
    try:
        species_resp = requests.get(data["species"]["url"], timeout=10)
        if species_resp.status_code == 200:
            sp = species_resp.json()
            gen_url = sp.get("generation", {}).get("url", "")
            if gen_url:
                gen_id = int(gen_url.rstrip("/").split("/")[-1])
                gen_nombre = GENERACION_NOMBRES.get(gen_id, f"Generacion {gen_id}")
                generacion = gen_nombre
    except Exception:
        pass

    dispatcher.utter_message(text=f"{pokemon_nombre} pertenece a la {generacion}.")
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "generacion_pokemon")]


def _hacer_consulta_dato_curioso(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    
    descripcion = ""
    try:
        species_resp = requests.get(data["species"]["url"], timeout=10)
        if species_resp.status_code == 200:
            sp = species_resp.json()
            # Buscar descripción en español
            for entry in sp.get("flavor_text_entries", []):
                if entry["language"]["name"] == "es":
                    descripcion = entry["flavor_text"].replace("\n", " ").replace("\f", " ")
                    break
            if not descripcion:
                for entry in sp.get("flavor_text_entries", []):
                    if entry["language"]["name"] == "en":
                        descripcion = entry["flavor_text"].replace("\n", " ").replace("\f", " ")
                        break
    except Exception:
        pass

    if descripcion:
        dispatcher.utter_message(text=f"Sabias esto sobre {pokemon_nombre}? {descripcion}")
    else:
        dispatcher.utter_message(text=f"No tengo datos curiosos especificos sobre {pokemon_nombre} en este momento.")
    
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "dato_curioso")]


def _hacer_consulta_dato(dispatcher, nombre_sanitizado):
    data = consultar_pokeapi(nombre_sanitizado)
    if not data:
        manejar_error_pokemon(dispatcher, nombre_sanitizado, "no_encontrado")
        return []
    pokemon_nombre = data["name"].capitalize()
    pokemon_id = data["id"]
    tipos = ", ".join(traducir_tipo_a_espanol(t["type"]["name"]) for t in data["types"])
    peso_kg = data["weight"] / 10
    altura_m = data["height"] / 10
    exp_base = data["base_experience"] or "Desconocida"

    datos_extra = ""
    try:
        species_resp = requests.get(data["species"]["url"], timeout=10)
        if species_resp.status_code == 200:
            sp = species_resp.json()
            descripcion = ""
            # Primero intentar español
            for entry in sp.get("flavor_text_entries", []):
                if entry["language"]["name"] == "es":
                    descripcion = entry["flavor_text"].replace("\n", " ").replace("\f", " ")
                    break
            # Si no hay español, intentar inglés
            if not descripcion:
                for entry in sp.get("flavor_text_entries", []):
                    if entry["language"]["name"] == "en":
                        descripcion = entry["flavor_text"].replace("\n", " ").replace("\f", " ")
                        break
            habitat = sp.get("habitat")
            habitat_name = habitat["name"].capitalize() if habitat else "Desconocido"
            color = sp.get("color", {}).get("name", "desconocido").capitalize()
            gen = sp.get("generation", {}).get("name", "").replace("generation-", "Gen ").upper()
            es_leg = "Si" if sp.get("is_legendary") else "No"
            es_mit = "Si" if sp.get("is_mythical") else "No"
            tasa = sp.get("capture_rate", "Desconocida")
            felicidad = sp.get("base_happiness", "Desconocida")
            datos_extra = (
                f"\nDescripcion: {descripcion}\nHabitat: {habitat_name}\n"
                f"Color: {color}\nGeneracion: {gen}\n"
                f"Legendario: {es_leg}\nMitico: {es_mit}\n"
                f"Tasa de captura: {tasa}/255\nFelicidad base: {felicidad}"
            )
    except Exception:
        pass

    mensaje = (
        f"Datos de {pokemon_nombre} (#{pokemon_id}):\n\n"
        f"Tipo(s): {tipos}\nPeso: {peso_kg} kg\n"
        f"Altura: {altura_m} m\nExperiencia base: {exp_base}{datos_extra}"
    )
    dispatcher.utter_message(text=mensaje)
    return [SlotSet("nombre_pokemon", nombre_sanitizado), SlotSet("ultima_consulta", "dato")]


# Mapa de funciones de consulta por tipo
CONSULTAS = {
    "pokemon": _hacer_consulta_pokemon,
    "peso": _hacer_consulta_peso,
    "altura": _hacer_consulta_altura,
    "estadistica": _hacer_consulta_estadistica,
    "habilidad": _hacer_consulta_habilidad,
    "dato": _hacer_consulta_dato,
    "tipo_pokemon": _hacer_consulta_tipo_pokemon,
    "id_pokemon": _hacer_consulta_id_pokemon,
    "generacion_pokemon": _hacer_consulta_generacion_pokemon,
    "dato_curioso": _hacer_consulta_dato_curioso,
}


# =============================================================================
# Custom Actions
# =============================================================================

class ActionConsultarPokemon(Action):
    def name(self) -> Text:
        return "action_consultar_pokemon"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_pokemon(dispatcher, nombre))


class ActionConsultarTipo(Action):
    def name(self) -> Text:
        return "action_consultar_tipo"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        # Si hay un nombre de pokemon en el mensaje, es probable que la intencion real 
        # sea consultar el tipo de ESE pokemon, no ver una lista.
        nombre_entidad = next(tracker.get_latest_entity_values("nombre_pokemon"), None)
        if nombre_entidad:
            return _hacer_consulta_tipo_pokemon(dispatcher, sanitizar_entrada(nombre_entidad))

        tipo = next(tracker.get_latest_entity_values("tipo_pokemon"), None)
        if not tipo:
            tipo = tracker.get_slot("tipo_pokemon")
        if not tipo:
            dispatcher.utter_message(text="No mencionaste ningun tipo de Pokemon. Decime un tipo, por ejemplo: fuego, agua, planta, electrico...")
            return []

        tipo_sanitizado = sanitizar_entrada(tipo)
        tipo_ingles = traducir_tipo_a_ingles(tipo_sanitizado)
        tipo_espanol = traducir_tipo_a_espanol(tipo_ingles)

        def consulta():
            response = requests.get(f"{POKEAPI_BASE_URL}/type/{tipo_ingles}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                pokemones = data["pokemon"][:30]
                lista = "\n".join(f"  - {p['pokemon']['name'].capitalize()}" for p in pokemones)
                total = len(data["pokemon"])
                mensaje = f"Pokemon de tipo {tipo_espanol} ({total} en total, mostrando 30):\n\n{lista}"
                if total > 30:
                    mensaje += f"\n\n... y {total - 30} mas. Queres saber mas sobre alguno de estos?"
                dispatcher.utter_message(text=mensaje)
                return [SlotSet("tipo_pokemon", tipo_sanitizado), SlotSet("ultima_consulta", "tipo")]
            elif response.status_code == 404:
                dispatcher.utter_message(text=f"No encontre el tipo '{tipo}'. Los tipos disponibles son: {', '.join(TIPOS_ES_EN.keys())}")
            else:
                manejar_error_pokemon(dispatcher, tipo, "api_error")
            return []

        return [FollowupAction("action_manejar_conducta")]


class ActionConsultarHabilidad(Action):
    def name(self) -> Text:
        return "action_consultar_habilidad"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_habilidad(dispatcher, nombre))


class ActionConsultarPeso(Action):
    def name(self) -> Text:
        return "action_consultar_peso"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_peso(dispatcher, nombre))


class ActionConsultarAltura(Action):
    def name(self) -> Text:
        return "action_consultar_altura"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_altura(dispatcher, nombre))


class ActionConsultarEstadistica(Action):
    def name(self) -> Text:
        return "action_consultar_estadistica"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_estadistica(dispatcher, nombre))


class ActionConsultarTipoPokemon(Action):
    def name(self) -> Text:
        return "action_consultar_tipo_pokemon"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_tipo_pokemon(dispatcher, nombre))


class ActionConsultarIdPokemon(Action):
    def name(self) -> Text:
        return "action_consultar_id_pokemon"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_id_pokemon(dispatcher, nombre))


class ActionConsultarGeneracionPokemon(Action):
    def name(self) -> Text:
        return "action_consultar_generacion_pokemon"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_generacion_pokemon(dispatcher, nombre))


class ActionConsultarDatoCurioso(Action):
    def name(self) -> Text:
        return "action_consultar_dato_curioso"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_dato_curioso(dispatcher, nombre))


class ActionConsultarDatoPokemon(Action):
    def name(self) -> Text:
        return "action_consultar_dato_pokemon"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = obtener_nombre_pokemon(tracker)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]
        return ejecutar_con_manejo_errores(dispatcher, nombre, lambda: _hacer_consulta_dato(dispatcher, nombre))


class ActionConsultarCantidadGeneracion(Action):
    def name(self) -> Text:
        return "action_consultar_cantidad_generacion"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        gen_texto = next(tracker.get_latest_entity_values("numero_generacion"), None)
        if not gen_texto:
            gen_texto = tracker.get_slot("numero_generacion")

        if not gen_texto:
            return [FollowupAction("action_manejar_conducta")]

        gen_limpio = sanitizar_entrada(gen_texto)
        gen_id = GENERACIONES_MAP.get(gen_limpio)

        if not gen_id:
            dispatcher.utter_message(text=f"No reconozco la generacion '{gen_texto}'.")
            return []

        def consulta():
            response = requests.get(f"{POKEAPI_BASE_URL}/generation/{gen_id}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                total = len(data.get("pokemon_species", []))
                gen_nombre = GENERACION_NOMBRES.get(gen_id, f"Generacion {gen_id}")
                dispatcher.utter_message(text=f"En la {gen_nombre} se agregaron un total de {total} Pokemon nuevos.")
                return [SlotSet("numero_generacion", gen_limpio), SlotSet("ultima_consulta", "cantidad_generacion")]
            return []

        return ejecutar_con_manejo_errores(dispatcher, "", consulta)


class ActionConsultarGeneracion(Action):
    """Consulta la PokeAPI para obtener info sobre una generacion de Pokemon."""

    def name(self) -> Text:
        return "action_consultar_generacion"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        gen_texto = next(tracker.get_latest_entity_values("numero_generacion"), None)
        if not gen_texto:
            gen_texto = tracker.get_slot("numero_generacion")

        # Si no hay entidad, mostrar lista de generaciones
        if not gen_texto:
            lista = "\n".join(f"  - Gen {num}: {nombre}" for num, nombre in GENERACION_NOMBRES.items())
            dispatcher.utter_message(
                text=f"Generaciones de Pokemon disponibles:\n\n{lista}\n\n"
                     f"Decime cual queres consultar, por ejemplo: 'Pokemon de la tercera generacion'"
            )
            return [SlotSet("ultima_consulta", "generacion")]

        gen_limpio = sanitizar_entrada(gen_texto)
        gen_id = GENERACIONES_MAP.get(gen_limpio)

        if not gen_id:
            dispatcher.utter_message(
                text=f"No reconozco la generacion '{gen_texto}'. "
                     f"Usa un numero del 1 al 9, o un nombre como 'primera', 'segunda', etc."
            )
            return []

        gen_nombre = GENERACION_NOMBRES.get(gen_id, f"Generacion {gen_id}")

        def consulta():
            response = requests.get(f"{POKEAPI_BASE_URL}/generation/{gen_id}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                especies = data.get("pokemon_species", [])
                total = len(especies)

                # Ordenar por ID extraido de la URL
                especies_ordenadas = sorted(
                    especies,
                    key=lambda x: int(x["url"].rstrip("/").split("/")[-1])
                )

                # Mostrar maximo 50
                mostrar = especies_ordenadas[:50]
                lista = "\n".join(
                    f"  - {e['name'].capitalize()} (#{e['url'].rstrip('/').split('/')[-1]})"
                    for e in mostrar
                )

                # Obtener tipos nuevos de esta generacion
                tipos_nuevos = data.get("types", [])
                tipos_texto = ""
                if tipos_nuevos:
                    tipos_lista = ", ".join(
                        traducir_tipo_a_espanol(t["name"]) for t in tipos_nuevos
                    )
                    tipos_texto = f"\nTipos introducidos: {tipos_lista}"

                gen_roman = ['', 'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix'][gen_id]
                mensaje = (
                    f"{gen_nombre} (generation-{gen_roman})\n\n"
                    f"Total de Pokemon nuevos: {total}{tipos_texto}\n\n"
                    f"Pokemon (mostrando {len(mostrar)} de {total}):\n{lista}"
                )

                if total > 50:
                    mensaje += f"\n\n... y {total - 50} mas."

                mensaje += "\n\nPreguntame sobre cualquiera de estos Pokemon para mas info."

                dispatcher.utter_message(text=mensaje)
                return [
                    SlotSet("numero_generacion", gen_limpio),
                    SlotSet("ultima_consulta", "generacion"),
                ]
            elif response.status_code == 404:
                dispatcher.utter_message(text=f"No encontre la generacion {gen_id}.")
            else:
                manejar_error_pokemon(dispatcher, "", "api_error")
            return []

        return ejecutar_con_manejo_errores(dispatcher, "", consulta)


class ActionConsultarOtroPokemon(Action):
    """
    Repite la ultima consulta pero con un Pokemon diferente.
    Si el usuario pregunto el peso de Charmander y luego dice 'y pikachu?',
    esta action consulta el peso de Pikachu.
    """

    def name(self) -> Text:
        return "action_consultar_otro_pokemon"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        nombre = next(tracker.get_latest_entity_values("nombre_pokemon"), None)
        if not nombre:
            return [FollowupAction("action_manejar_conducta")]

        nombre_sanitizado = sanitizar_entrada(nombre)
        if not nombre_sanitizado:
            manejar_error_pokemon(dispatcher, "", "nombre_invalido")
            return []

        # Determinar que consulta repetir
        ultima = tracker.get_slot("ultima_consulta") or "pokemon"

        # Buscar la funcion de consulta correspondiente
        funcion = CONSULTAS.get(ultima, _hacer_consulta_pokemon)

        return ejecutar_con_manejo_errores(
            dispatcher, nombre_sanitizado,
            lambda: funcion(dispatcher, nombre_sanitizado)
        )


class ActionManejarConducta(Action):
    """
    Maneja insultos y mensajes fuera de tema con un sistema de advertencias.
    - Insultos: +2 strikes (tolerancia cero)
    - Chit-chat/fuera de tema: +1 strike
    - 3 strikes -> conversacion pausada (el bot deja de responder)
    """

    def name(self) -> Text:
        return "action_manejar_conducta"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        advertencias_actual = tracker.get_slot("advertencias") or 0

        # Cada falta resta 1 vida (suma 1 al contador de advertencias)
        advertencias_actual += 1
        vidas_restantes = int(3 - advertencias_actual)

        if advertencias_actual >= 3:
            # Expulsar: pausar la conversacion
            dispatcher.utter_message(
                text="[SESION FINALIZADA]\n\n"
                     "Has perdido todas tus vidas por uso inapropiado del chat. "
                     "Este asistente es exclusivamente para consultas sobre Pokemon.\n\n"
                     "La sesion ha sido cerrada. No recibiras mas respuestas."
            )
            return [SlotSet("advertencias", advertencias_actual), ConversationPaused()]

        # Definir mensaje segun el intent
        nombre_detectado = obtener_nombre_pokemon(tracker)
        
        if intent == "insultar":
            motivo = "Los insultos no son tolerados."
        elif intent == "bot_challenge":
            motivo = "Soy un bot Pokemon y solo respondo dudas sobre el juego."
        elif intent == "chit_chat":
            motivo = "Ese mensaje no tiene que ver con Pokemon."
        elif not nombre_detectado and intent != "saludar" and intent != "despedir" and intent != "agradecer":
            motivo = "No mencionaste ningun Pokemon o informacion necesaria en tu mensaje."
        else:
            motivo = "No entiendo tu mensaje o esta fuera de tema."

        mensaje = (
            f"[ADVERTENCIA]\n\n"
            f"{motivo} Este chat es exclusivamente para consultas sobre Pokemon.\n\n"
            f"Vidas restantes: {vidas_restantes}/3\n\n"
            "Si llegas a 0 vidas, la conversacion sera finalizada permanentemente. "
            "Preguntame sobre Pokemon, por ejemplo: 'Contame sobre Pikachu'"
        )

        dispatcher.utter_message(text=mensaje)
        return [SlotSet("advertencias", advertencias_actual)]
    
# class ActionSessionStart(Action):
#     def name(self) -> Text:
#         return "action_session_start"

#     async def run(
#       self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
#     ) -> List[Dict[Text, Any]]:
        
#         # Envía el mensaje de bienvenida
#         dispatcher.utter_message(text="¡Bienvenido! Soy tu asistente Pokémon. Puedo darte info sobre cualquier Pokémon, tipos o generaciones. ¿En qué puedo ayudarte hoy?")
        
#         # Indica a Rasa que la sesión inició y que quede escuchando (action_listen)
#         return [SessionStarted(), ActionExecuted("action_listen")]