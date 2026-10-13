"""
Hugging Face Multilingual Civic AI System
Supports:
- Kannada (kn - ಕನ್ನಡ)
- Hindi (hi - हिंदी)
- Telugu (te - తెలుగు)
- English (en)

Provides:
- High-speed deterministic Unicode script detection
- Multilingual civic issue classification & priority routing
- Resilient on-demand translation with Hugging Face InferenceClient + zero-latency civic translation memory fallback
"""

import os
import re
from typing import Dict, Tuple, Any

SUPPORTED_LANGUAGES = {
    'en': 'English',
    'kn': 'ಕನ್ನಡ (Kannada)',
    'hi': 'हिंदी (Hindi)',
    'te': 'తెలుగు (Telugu)'
}

# =====================================================================
# 1. High-Speed Unicode Script & Language Detector
# =====================================================================

def detect_language(text: str) -> str:
    """
    Detects language based on Unicode script block ranges.
    Returns: 'kn' (Kannada), 'hi' (Hindi/Devanagari), 'te' (Telugu), or 'en' (English/Latin).
    """
    if not text or not isinstance(text, str):
        return 'en'

    kannada_count = 0
    devanagari_count = 0
    telugu_count = 0
    latin_count = 0

    for char in text:
        cp = ord(char)
        if 0x0C80 <= cp <= 0x0CFF:
            kannada_count += 1
        elif 0x0900 <= cp <= 0x097F:
            devanagari_count += 1
        elif 0x0C00 <= cp <= 0x0C7F:
            telugu_count += 1
        elif 0x0041 <= cp <= 0x005A or 0x0061 <= cp <= 0x007A:
            latin_count += 1

    counts = {
        'kn': kannada_count,
        'hi': devanagari_count,
        'te': telugu_count,
        'en': latin_count
    }

    max_lang = max(counts, key=lambda k: counts[k])
    if counts[max_lang] > 0:
        return max_lang
    return 'en'

# =====================================================================
# 2. Multilingual Civic Issue Classification
# =====================================================================

CIVIC_KEYWORDS = {
    'pothole': {
        'en': ['pothole', 'crater', 'asphalt', 'tarmac', 'road damage', 'broken road', 'street damage', 'bump', 'pit'],
        'kn': ['ಗುಂಡಿ', 'ರಸ್ತೆ', 'ಹಾಳಾದ ರಸ್ತೆ', 'ತಗ್ಗು', 'ಹಳ್ಳ', 'ರಸ್ತೆ ಗುಂಡಿ', 'ಡಾಂಬರು'],
        'hi': ['गड्ढा', 'गड्ढे', 'सड़क', 'टूटी सड़क', 'मार्ग', 'खड्डे', 'सड़क क्षति'],
        'te': ['గుంత', 'గుంతలు', 'రోడ్డు', 'పాడైన రోడ్డు', 'రహదారి', 'గొయ్యి']
    },
    'garbage': {
        'en': ['garbage', 'trash', 'waste', 'litter', 'dump', 'bin', 'refuse', 'stink', 'smell', 'debris', 'filth'],
        'kn': ['ಕಸ', 'ತ್ಯಾಜ್ಯ', 'ಕಸದ ಬುಟ್ಟಿ', 'ವಾಸನೆ', 'ದುರ್ವಾಸನೆ', 'ಕಸದ ರಾಶಿ', 'ಕೊಳಕು'],
        'hi': ['कचरा', 'कूड़ा', 'कचरे का ढेर', 'दुर्गंध', 'बदबू', 'कूड़ेदान', 'गंदगी'],
        'te': ['చెత్త', 'వ్యర్థాలు', 'కంపు', 'దుర్వాసన', 'చెత్త కుప్ప', 'చెత్తబుట్ట']
    },
    'drainage': {
        'en': ['drain', 'drainage', 'sewer', 'leak', 'overflow', 'flooding', 'flood', 'clog', 'water log', 'gutter', 'pipeline'],
        'kn': ['ಚರಂಡಿ', 'ಒಳಚರಂಡಿ', 'ನೀರು ನಿಂತಿದೆ', 'ಸೋರಿಕೆ', 'ಮಳೆನೀರು', 'ಚರಂಡಿ ನೀರು', 'ಕಾಲುವೆ'],
        'hi': ['नाली', 'नालियां', 'सीवर', 'जलभराव', 'गटर', 'पानी का रिसाव', 'बाढ़', 'गंदा पानी'],
        'te': ['కాలువ', 'డ్రైనేజీ', 'మురుగు ನೀರು', 'వరద', 'నీటి లీకేజీ', 'మురుగు కాలువ']
    },
    'street_light': {
        'en': ['street_light', 'street light', 'lamp', 'bulb', 'outage', 'darkness', 'dark', 'pole', 'electric wire', 'streetlight'],
        'kn': ['ಬೀದಿ ದೀಪ', 'ದೀಪ', 'ಕತ್ತಲು', 'ವಿದ್ಯುತ್', 'ಬೆಳಕು ಇಲ್ಲ', 'ಕಂಬ'],
        'hi': ['स्ट्रीट लाइट', 'बिजली', 'अंधेरा', 'बत्ती', 'तार', 'लाइट खराब', 'खंभा'],
        'te': ['వీధి దీపం', 'దీపం', 'చీకటి', 'విద్యుత్', 'వెలుగు లేదు', 'స్తంభం']
    }
}

HIGH_PRIORITY_KEYWORDS = {
    'en': ['accident', 'crash', 'injury', 'danger', 'dangerous', 'emergency', 'deep', 'main road', 'highway', 'traffic', 'hazard', 'fire', 'severe', 'urgent'],
    'kn': ['ಅಪಘಾತ', 'ಅಪಾಯ', 'ತುರ್ತು', 'ಗಂಭೀರ', 'ಮುಳುಗಿದೆ', 'ಅಪಾಯಕಾರಿ', 'ಹೆದ್ದಾರಿ'],
    'hi': ['दुर्घटना', 'खतरा', 'खतरनाक', 'आपातकालीन', 'गंभीर', 'चोट', 'राजमार्ग', 'जलमग्न'],
    'te': ['ప్రమాదం', 'భద్రత', 'అత్యవసరం', 'తీవ్రమైన', 'ముంపు', 'ప్రమాదకరమైన', 'రహదారి']
}

def classify_complaint_multilingual(text: str, title: str = "") -> Dict[str, Any]:
    """
    Classifies civic complaints across Kannada, Hindi, Telugu, and English.
    Returns:
        {
            'category': 'pothole' | 'garbage' | 'drainage' | 'street_light' | 'other',
            'priority': 'High' | 'Medium' | 'Low',
            'language': 'en' | 'kn' | 'hi' | 'te',
            'confidence': float
        }
    """
    combined = f"{title} {text}".lower().strip()
    detected_lang = detect_language(combined)

    matched_category = 'other'
    highest_matches = 0

    for cat, lang_dict in CIVIC_KEYWORDS.items():
        count = 0
        target_lists = [lang_dict.get(detected_lang, []), lang_dict.get('en', [])]
        for kw_list in target_lists:
            for kw in kw_list:
                if kw in combined:
                    count += 1
        if count > highest_matches:
            highest_matches = count
            matched_category = cat

    # Determine priority
    priority = 'Medium'
    is_high_prio = False

    prio_keywords = HIGH_PRIORITY_KEYWORDS.get(detected_lang, []) + HIGH_PRIORITY_KEYWORDS['en']
    if any(kw in combined for kw in prio_keywords):
        is_high_prio = True

    if matched_category == 'drainage':
        priority = 'High'
    elif matched_category == 'pothole':
        priority = 'High' if is_high_prio else 'Medium'
    elif matched_category == 'garbage':
        priority = 'High' if is_high_prio else ('Medium' if any(w in combined for w in ['overflow', 'stink', 'smell', 'ವಾಸನೆ', 'बदबू', 'కంపు']) else 'Low')
    elif matched_category == 'street_light':
        priority = 'Medium' if (is_high_prio or any(w in combined for w in ['dark', 'complete', 'ಕತ್ತಲು', 'अंधेरा', 'చీకటి'])) else 'Low'
    elif matched_category == 'other':
        priority = 'High' if is_high_prio else 'Low'

    confidence = 0.92 if highest_matches > 0 else 0.70

    return {
        'category': matched_category,
        'priority': priority,
        'language': detected_lang,
        'confidence': confidence
    }

# =====================================================================
# 3. On-Demand Translation Engine
# =====================================================================

CIVIC_DICTIONARY = {
    'kn': {
        'pothole': 'ರಸ್ತೆ ಗುಂಡಿ',
        'road damage': 'ಹಾಳಾದ ರಸ್ತೆ',
        'garbage': 'ಕಸ',
        'trash': 'ಕಸದ ರಾಶಿ',
        'drainage': 'ಚರಂಡಿ',
        'street light': 'ಬೀದಿ ದೀಪ',
        'broken': 'ಮುರಿದಿದೆ',
        'overflowing': 'ಉಕ್ಕಿ ಹರಿಯುತ್ತಿದೆ',
        'submitted': 'ಸಲ್ಲಿಸಲಾಗಿದೆ',
        'verified': 'ಪರಿಶೀಲಿಸಲಾಗಿದೆ',
        'assigned': 'ನಿಯೋಜಿಸಲಾಗಿದೆ',
        'in progress': 'ಪ್ರಗತಿಯಲ್ಲಿದೆ',
        'completed': 'ಪೂರ್ಣಗೊಂಡಿದೆ',
        'resolved': 'ಪರಿಹರಿಸಲಾಗಿದೆ',
        'closed': 'ಮುಕ್ತಾಯಗೊಂಡಿದೆ',
        'high': 'ಹೆಚ್ಚಿನ ಆದ್ಯತೆ',
        'medium': 'ಮಧ್ಯಮ ಆದ್ಯತೆ',
        'low': 'ಕಡಿಮೆ ಆದ್ಯತೆ'
    },
    'hi': {
        'pothole': 'सड़क का गड्ढा',
        'road damage': 'टूटी सड़क',
        'garbage': 'कचरा',
        'trash': 'कूड़ा',
        'drainage': 'नाली / सीवर',
        'street light': 'स्ट्रीट लाइट',
        'broken': 'टूटा हुआ',
        'overflowing': 'ओवरफ्लो हो रहा है',
        'submitted': 'जमा किया गया',
        'verified': 'सत्यापित',
        'assigned': 'आवंटित',
        'in progress': 'प्रगति पर है',
        'completed': 'पूर्ण',
        'resolved': 'समाधान हो गया',
        'closed': 'बंद',
        'high': 'उच्च प्राथमिकता',
        'medium': 'मध्यम प्राथमिकता',
        'low': 'कम प्राथमिकता'
    },
    'te': {
        'pothole': 'రోడ్డు గుంత',
        'road damage': 'పాడైన రోడ్డు',
        'garbage': 'చెత్త',
        'trash': 'చెత్తకుప్ప',
        'drainage': 'డ్రైనేజీ / మురుగుకాలువ',
        'street light': 'వీధి దీపం',
        'broken': 'పాడైపోయింది',
        'overflowing': 'పొంగిపొర్లుతోంది',
        'submitted': 'సమర్పించబడింది',
        'verified': 'ధృవీకరించబడింది',
        'assigned': 'కేటాయించబడింది',
        'in progress': 'పురోగతిలో ఉంది',
        'completed': 'పూర్తయింది',
        'resolved': 'పరిష్కరించబడింది',
        'closed': 'ముగిసింది',
        'high': 'అధిక ప్రాధాన్యత',
        'medium': 'మధ్యస్థ ప్రాధాన్యత',
        'low': 'తక్కువ ప్రాధాన్యత'
    }
}

REVERSE_CIVIC_DICTIONARY = {}
for lang_code, mapping in CIVIC_DICTIONARY.items():
    for en_phrase, localized_phrase in mapping.items():
        REVERSE_CIVIC_DICTIONARY[localized_phrase] = en_phrase

def _translate_with_huggingface(text: str, source_lang: str, target_lang: str) -> str:
    """Attempts serverless Hugging Face Inference if token is configured."""
    hf_token = os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_API_KEY')
    if not hf_token:
        return ""
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=hf_token, timeout=4.0)
        prompt = f"Translate the following civic complaint text from {source_lang} to {target_lang}. Only output the direct translation with no explanations:\n\n{text}"
        res = client.text_generation(
            prompt,
            model="facebook/mbart-large-50-many-to-many-mmt",
            max_new_tokens=150
        )
        clean_res = res.strip()
        if clean_res:
            return clean_res
    except Exception:
        pass
    return ""

def translate_text(text: str, source_lang: str = "auto", target_lang: str = "en") -> Dict[str, Any]:
    """
    Translates text between English and Kannada/Hindi/Telugu.
    Returns:
        {
            'translated_text': str,
            'source_lang': str,
            'target_lang': str,
            'engine': str
        }
    """
    if not text:
        return {'translated_text': '', 'source_lang': 'en', 'target_lang': target_lang, 'engine': 'identity'}

    if not source_lang or source_lang == 'auto':
        source_lang = detect_language(text)

    if source_lang == target_lang:
        return {
            'translated_text': text,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'engine': 'identity'
        }

    # 1. Try Hugging Face API if token available
    hf_translation = _translate_with_huggingface(text, source_lang, target_lang)
    if hf_translation:
        return {
            'translated_text': hf_translation,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'engine': 'huggingface'
        }

    # 2. Resilient domain translation memory fallback
    translated = text
    if target_lang == 'en':
        for regional_phrase, en_phrase in sorted(REVERSE_CIVIC_DICTIONARY.items(), key=lambda x: -len(x[0])):
            if regional_phrase in translated:
                translated = translated.replace(regional_phrase, en_phrase)
        if translated == text:
            classification = classify_complaint_multilingual(text)
            cat_name = classification['category'].replace('_', ' ').title()
            translated = f"[{SUPPORTED_LANGUAGES.get(source_lang, source_lang)} report: {cat_name} issue] {text}"
    else:
        lang_dict = CIVIC_DICTIONARY.get(target_lang, {})
        for en_phrase, regional_phrase in sorted(lang_dict.items(), key=lambda x: -len(x[0])):
            pattern = re.compile(re.escape(en_phrase), re.IGNORECASE)
            translated = pattern.sub(regional_phrase, translated)

    return {
        'translated_text': translated,
        'source_lang': source_lang,
        'target_lang': target_lang,
        'engine': 'civic_translation_memory'
    }
