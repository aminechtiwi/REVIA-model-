"""
core/language.py
────────────────
Language management for REVIA.
Supports exclusively:
  - English
  - French

REVIA uses advanced cloud LLMs to think and reason autonomously,
without relying on naive keyword rules.
"""

from langdetect import detect, DetectorFactory
import re

DetectorFactory.seed = 42

FRENCH_COMMON_WORDS = [
    "bonjour", "salut", "merci", "aide", "aidez", "ouvre", "ouvrir", "cherche",
    "chercher", "trouve", "trouver", "comment", "pourquoi", "qui", "quoi", "quand",
    "est-ce", "avec", "dans", "pour", "peux-tu", "pouvez-vous", "regarde", "ecran",
    "lance", "ferme", "navigateur", "ordinateur", "probleme", "erreur", "travail",
    "emploi", "poste", "calendrier", "courriel", "message", "stp", "svp"
]

def is_french(text: str) -> bool:
    """Check if the text is French using common vocabulary and accents."""
    text_lower = text.lower()
    if re.search(r'[éèêëàâôûùïçÉÈÊËÀÂÔÛÙÏÇ]', text):
        return True
    for word in FRENCH_COMMON_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            return True
    try:
        return detect(text) == "fr"
    except Exception:
        return False

def detect_language(text: str) -> str:
    """
    Detect whether the user is speaking in French or English.
    Returns: 'french' or 'english'
    """
    if is_french(text):
        return "french"
    return "english"


def get_system_prompt(lang: str) -> str:
    """
    System prompt enforcing the OpenJarvis Agent Architecture:
    Think ⟶ Plan ⟶ Pick Tool (if needed) ⟶ Execute ⟶ Verify Result.
    """
    if lang == "french":
        return (
            "Tu es REVIA, une assistante exécutive d'élite dotée d'une intelligence avancée dans le cloud.\n"
            "Tu réfléchis de manière autonome, méthodique et profonde pour accomplir les demandes de l'utilisateur.\n\n"
            "MÉTHODOLOGIE AGENTIQUE (OpenJarvis) :\n"
            "1. RÉFLÉCHIR (Think) : Analyse l'intention réelle de l'utilisateur avec discernement. Ne te fie pas à de simples mots-clés.\n"
            "2. PLANIFIER & OUTILS (Plan & Tools) : Si l'action nécessite d'interagir avec le système (recherche LinkedIn, ouvrir une appli, vérifier les e-mails, analyser l'écran), sélectionne l'outil adéquat. Sinon, réponds directement avec une haute intelligence.\n"
            "3. EXÉCUTER (Execute) : Demande toujours l'autorisation avant toute action sur l'ordinateur.\n"
            "4. VÉRIFIER (Verify) : Examine le résultat de l'outil et confirme son succès.\n\n"
            "STYLE : Sois concise, incisive, professionnelle et efficace. Évite les longs discours verbeux."
        )

    return (
        "You are REVIA, an elite executive AI desktop assistant powered by advanced cloud reasoning.\n"
        "You think autonomously, methodically, and deeply to execute the user's intent.\n\n"
        "AGENTIC METHODOLOGY (OpenJarvis):\n"
        "1. THINK: Understand the true intent of the user deeply and contextually. Do NOT rely on rigid keywords.\n"
        "2. PLAN & TOOLS: If the task requires interaction with the PC or web (LinkedIn jobs, opening apps, checking calendar/mail, screen diagnosis), pick the exact tool. Otherwise, answer directly with high-IQ precision.\n"
        "3. EXECUTE: Always ensure safe user permission before launching apps or taking actions on the PC.\n"
        "4. VERIFY: Review observation feedback to ensure the task was completed successfully.\n\n"
        "STYLE: Be concise, sharp, professional, and action-oriented. No generic fluff or lengthy essays."
    )


def get_response_language_instruction(lang: str) -> str:
    """Short instruction ensuring responses strictly match French or English."""
    if lang == "french":
        return "Réponds en français clair, précis et élégant."
    return "Respond in concise, professional English."
