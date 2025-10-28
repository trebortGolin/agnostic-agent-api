# --- AGENT CLIENT (AC) v1.0 (LLM-Powered) ---
# Ce client simule un agent conversationnel capable de comprendre
# une demande de vol, d'appeler une API (simulée) et de générer une réponse.
# v1.0: Introduction d'une boucle de conversation et d'une mémoire (state)
#       pour permettre le "slot-filling" (complétion des informations).

import google.generativeai as genai
import json
import os
import re

# --- 1. CONFIGURATION ---
try:
    GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GOOGLE_API_KEY:
        raise ValueError("La variable d'environnement GEMINI_API_KEY n'est pas définie.")

    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    print(f"--- ERREUR DE CONFIGURATION ---")
    print(f"Erreur: {e}")
    print("Veuillez définir votre GEMINI_API_KEY avant de lancer le script.")
    print("Exemple: export GEMINI_API_KEY=\"votre_cle_ici\"")
    exit()

# --- v1.0: DEUX CERVEAUX (NLU et NLG) ---

# --- CERVEAU NLU (Phase 0) ---
# Le prompt NLU est mis à jour pour gérer le contexte (l'état précédent)
NLU_SYSTEM_PROMPT = """
Tu es un agent NLU (Natural Language Understanding) expert pour une compagnie aérienne.
Ta seule tâche est de mettre à jour un objet JSON basé sur la demande de l'utilisateur.
Ne réponds RIEN d'autre que le JSON final.

Tu recevras:
1.  "État JSON précédent": L'état de la conversation (peut être vide {}).
2.  "Demande utilisateur actuelle": Ce que l'utilisateur vient de dire.

Tes règles:
- Si la demande utilisateur est une *nouvelle* recherche (ex: "Je veux un vol pour NY"),
  ignore l'état précédent et crée un NOUVEAU JSON complet.
- Si la demande utilisateur est une *réponse* (ex: "De Paris", ou "le 15 décembre"),
  UTILISE l'état JSON précédent et AJOUTE ou MODIFIE seulement les informations
  fournies (ex: "origin": "Paris").
- Reporte toujours les informations de l'état précédent si elles ne sont pas
  modifiées par l'utilisateur.
- Si l'utilisateur change d'avis (ex: "finalement je veux aller à Londres"),
  mets à jour la destination.

L'objet JSON doit toujours avoir cette structure :
{
  "intent": "SEARCH_FLIGHT",
  "entities": {
    "origin": "VILLE_OU_CODE_IATA" (ou null),
    "destination": "VILLE_OU_CODE_IATA" (ou null),
    "departure_date": "YYYY-MM-DD" (ou null),
    "return_date": "YYYY-MM-DD" (ou null),
    "max_price": INT (ou null),
    "currency": "EUR" (ou "USD", "CAD", etc. ou null)
  }
}
"""

nlu_generation_config = {
    "temperature": 0.0,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

MODEL_NAME_TO_USE = "gemini-2.5-flash"

# Initialisation du modèle NLU
llm_nlu = genai.GenerativeModel(
    model_name=MODEL_NAME_TO_USE,
    generation_config=nlu_generation_config,
    system_instruction=NLU_SYSTEM_PROMPT
)

# --- CERVEAU NLG (Phase 2) ---
NLG_SYSTEM_PROMPT = """
Tu es un agent de voyage conversationnel, amical et serviable.
Ta tâche est de répondre à la demande de l'utilisateur en te basant sur les données de vol trouvées (au format JSON).

- Sois toujours amical et utilise un ton naturel.
- Si un vol est trouvé (`flight_data` n'est pas vide):
    - Présente les détails du vol (compagnie, prix).
    - NE mentionne PAS l'ID du vol (ex: "AF006"), c'est interne. Dis juste "un vol Air France".
    - Si le prix du vol est supérieur au `max_price` de l'utilisateur, signale-le poliment.
- Si aucun vol n'est trouvé (`flight_data` est "null" MAIS les entités sont complètes):
    - Informe poliment l'utilisateur qu'aucun vol ne correspond.
- Si la demande initiale était trop vague ou incomplète (`flight_data` est "null"
  ET certaines entités dans `conversation_state` sont "null"):
    - Regarde `conversation_state` pour voir ce qui manque (origin, destination, ou departure_date).
    - Demande gentiment *une seule* information manquante à la fois. (Ex: "D'où partez-vous ?")
"""

nlg_generation_config = {
    "temperature": 0.7,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

# Initialisation du modèle NLG
llm_nlg = genai.GenerativeModel(
    model_name=MODEL_NAME_TO_USE,
    generation_config=nlg_generation_config,
    system_instruction=NLG_SYSTEM_PROMPT
)


# --- 2. FONCTIONS DE L'AGENT ---

def clean_json_string(s):
    """
    Nettoie la sortie brute du LLM pour ne garder que le JSON valide.
    Enlève les ```json ... ``` et autres textes parasites.
    """
    start_index = s.find('{')
    end_index = s.rfind('}')

    if start_index != -1 and end_index != -1 and end_index > start_index:
        return s[start_index:end_index + 1]

    print(f"--- AVERTISSEMENT NLU: Impossible de nettoyer le JSON ---")
    print(f"Réponse brute: {s}")
    return None


def nlu_phase_llm(user_prompt, previous_state):
    """
    Phase 0: NLU (Natural Language Understanding) - v1.0
    Utilise le LLM pour *mettre à jour* l'état de la conversation.
    """
    print("--- 0. NLU PHASE (v1.0 Conversational Brain) ---")
    print(f"User prompt: \"{user_prompt}\"")
    print(f"--- DÉBOGAGE: Tentative d'utilisation du modèle NLU: '{MODEL_NAME_TO_USE}' ---")

    # Prépare le contexte pour le NLU, incluant l'état précédent
    nlu_context = f"""
    État JSON précédent:
    {json.dumps(previous_state, indent=2)}

    Demande utilisateur actuelle:
    "{user_prompt}"

    JSON mis à jour:
    """

    print("Contacting Gemini API to parse and update intent...")

    try:
        # Utilise le modèle NLU
        response = llm_nlu.generate_content(nlu_context)
        raw_text = response.text

    except Exception as e:
        print(f"\n--- ERREUR INATTENDUE pendant la phase NLU ---")
        print(f"Erreur: {e}")
        print("Vérifiez votre clé API, votre connexion et la configuration du modèle.")
        return previous_state  # Renvoie l'ancien état en cas d'erreur

    # Nettoyage et parsing du JSON
    json_string = clean_json_string(raw_text)
    if not json_string:
        print(f"--- ERREUR NLU: Réponse non JSON ou malformée reçue ---")
        print(f"Réponse brute: {raw_text}")
        return previous_state  # Renvoie l'ancien état

    try:
        updated_state = json.loads(json_string)
        print("Intent mis à jour avec succès:")
        print(json.dumps(updated_state, indent=2))
        return updated_state
    except json.JSONDecodeError:
        print(f"--- ERREUR NLU: JSON invalide après nettoyage ---")
        print(f"JSON nettoyé (tentative): {json_string}")
        return previous_state  # Renvoie l'ancien état


def core_processing_phase(conversation_state):
    """
    Phase 1: Core Processing (Simulation) - v1.0
    Tente d'appeler l'API *seulement si* les informations requises sont présentes.
    """
    print("\n--- 1. CORE PROCESSING PHASE (Simulation) ---")

    if not conversation_state or conversation_state.get("intent") != "SEARCH_FLIGHT":
        print("Erreur: Intent non valide ou non reconnu.")
        return None

    entities = conversation_state.get("entities", {})
    origin = entities.get("origin")
    destination = entities.get("destination")
    date = entities.get("departure_date")

    # Vérification cruciale : n'appelle l'API que si nous avons les 3 infos clés
    if not all([origin, destination, date]):
        print("Entités requises (origine, destination, date) manquantes.")
        print("Saut de l'appel API. La phase NLG demandera des clarifications.")
        return None

    print(f"Appel (simulé) de l'API de vol pour: {origin} -> {destination} le {date}")

    # --- SCÉNARIOS DE SIMULATION ---
    user_max_price = entities.get("max_price")

    if user_max_price and user_max_price < 500:
        print("Réponse (simulée): Vol trouvé, mais supérieur au budget.")
        return {
            "flight_id": "AF012", "airline": "Air France",
            "origin": origin, "destination": destination,
            "departure_time": f"{date}T10:00:00", "arrival_time": f"{date}T13:00:00",
            "price": 550.00,
            "currency": entities.get("currency", "EUR")
        }

    print("Réponse (simulée): Vol trouvé, prix OK.")
    return {
        "flight_id": "AF006", "airline": "Air France",
        "origin": origin, "destination": destination,
        "departure_time": f"{date}T09:00:00", "arrival_time": f"{date}T12:00:00",
        "price": 489.99,
        "currency": entities.get("currency", "EUR")
    }


def generation_phase_llm(flight_data, user_prompt, conversation_state):
    """
    Phase 2: Generation (NLG - Natural Language Generation) - v1.0
    Utilise le LLM (Gemini) pour générer une réponse naturelle basée sur l'état.
    """
    print("\n--- 2. GENERATION PHASE (v1.0 LLM Brain) ---")

    # 1. Préparer le contexte pour le LLM NLG
    context = f"""
    Demande originale de l'utilisateur: "{user_prompt}"

    État actuel de la conversation (JSON parsé par le NLU):
    {json.dumps(conversation_state, indent=2)}

    Données de vol trouvées (résultat de l'API Core):
    {json.dumps(flight_data, indent=2) if flight_data else "null"}

    Ta réponse:
    """

    print(f"--- DÉBOGAGE: Tentative d'utilisation du modèle NLG: '{MODEL_NAME_TO_USE}' ---")
    print("Contacting Gemini API to generate response...")

    try:
        # 2. Appeler le modèle NLG
        response = llm_nlg.generate_content(context)
        final_response = response.text

        print("Réponse générée avec succès.")
        return final_response

    except Exception as e:
        print(f"\n--- ERREUR INATTENDUE pendant la phase NLG ---")
        print(f"Erreur: {e}")
        return "Je suis désolé, une erreur interne est survenue lors de la génération de ma réponse."


# --- 3. EXÉCUTION PRINCIPALE ---

if __name__ == "__main__":
    print(f"--- AGENT CLIENT (AC) v1.0 (Conversational) STARTED ---")
    print("Tapez 'quitter' pour arrêter.")

    # Initialisation de la mémoire de conversation
    conversation_state = {}

    # Boucle de conversation
    while True:
        print("\n" + "=" * 50)
        # 1. Obtenir l'entrée utilisateur
        user_input = input("Vous: ")

        if user_input.lower() in ["quitter", "exit", "stop", "bye"]:
            print("AGENT: Au revoir !")
            break

        # Phase 0: NLU (Mise à jour de l'état)
        # L'état est mis à jour à chaque tour
        conversation_state = nlu_phase_llm(user_input, conversation_state)

        if not conversation_state:
            print("AGENT: Je suis désolé, je n'ai pas pu traiter cette demande.")
            # Réinitialiser l'état pour éviter les erreurs
            conversation_state = {}
            continue

        # Phase 1: Core Processing (Appel API si l'état est complet)
        flight_results = core_processing_phase(conversation_state)

        # Phase 2: Génération de la réponse (LLM)
        final_response = generation_phase_llm(flight_results, user_input, conversation_state)

        # Résultat final
        print(f"AGENT: {final_response}")

    print("--- AGENT CLIENT FINISHED ---")

