/**
 * Transcript Translation & Romanization (Transliteration) Utilities
 * 
 * Supports:
 * 1. 'romanized' (English script, same spoken language, e.g. "Namaskara Harshith...")
 * 2. 'translated' (Full English translation, e.g. "Hello Harshith, this is today's weather...")
 * 3. 'original' (Original native script: Kannada, Hindi, Telugu, English)
 * 
 * Fully compatible with:
 * - Live Sarvam Voice Agent analytics & transcripts ({ role: 'agent'|'user', content, language_name })
 * - Gate Zero telephony campaign outputs (Telugu, Kannada, Hindi, English)
 * - SQLite simulated and webhook call transcripts ({ speaker: 'Agent'|'Farmer', text })
 */

// Comprehensive phrase dictionaries for natural, idiomatic transliterations & translations
const PHRASE_PATTERNS = [
  // 1. KANNADA GREETING (Orchestrator variant)
  {
    regex: /ನಮಸ್ಕಾರ\s+([^,]+),\s*ಇದು ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್‌ನಿಂದ\s+([^ಗ]+)ಗೆ ಇಂದಿನ ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ[।\.]*\s*ಇಂದಿನ ತಾಪಮಾನ\s*([0-9.]+)[°\s]*C,\s*ಗಾಳಿಯ ವೇಗ\s*([0-9.]+)\s*ಕಿಮೀ\/ಗಂಟೆ,\s*ಮಳೆಯ ಸಾಧ್ಯತೆ\s*([0-9.]+)%\s*ಮತ್ತು ತೇವಾಂಶ\s*([0-9.]+)%\s*ಆಗಿದೆ[।\.]*\s*ಹವಾಮಾನದ ಕುರಿತು ಯಾವುದೇ ಪ್ರಶ್ನೆಗಳಿವೆಯೇ\?/i,
    romanized: (m) => `Namaskara ${m[1].trim()}, idu Agrythm Connect ninda ${m[2].trim()} ge indina havamana munsuchane. Indina tapamana ${m[3].trim()}°C, galiya vega ${m[4].trim()} km/h, maleya sadhyate ${m[5].trim()}% mattu tevamsha ${m[6].trim()}% agide. Havamanada kuritu yavude prashnegaliveye?`,
    translated: (m) => `Hello ${m[1].trim()}, this is today's weather forecast for ${m[2].trim()} from Agrythm Connect. Today's temperature is ${m[3].trim()}°C, wind speed is ${m[4].trim()} km/h, precipitation probability is ${m[5].trim()}%, and humidity is ${m[6].trim()}%. Do you have any questions regarding today's weather?`
  },
  // 2. KANNADA GREETING (Weathercall script variant)
  {
    regex: /ನಮಸ್ಕಾರ\s+([^\s]+)\s+ಅವರೇ[।\.]*\s*ನಾನು ಅಗ್ರಿದಮ್‌ನಿಂದ ಹವಾಮಾನ ತಿಳಿಸಲು ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ[।\.]*\s*ಇಂದು\s+([^\s]+)\s+ಪ್ರದೇಶದ ಹವಾಮಾನ ಮಾಹಿತಿ ಇದು[।\.]*\s*ತಾಪಮಾನ\s*([0-9.]+)\s*ರಿಂದ\s*([0-9.]+)\s*ಡಿಗ್ರಿ ನಡುವೆ ಇರುತ್ತದೆ[।\.]*\s*ಗಾಳಿಯ ವೇಗ ಗಂಟೆಗೆ\s*([0-9.]+)\s*ಕಿಲೋಮೀಟರ್ ವರೆಗೆ ಇರುತ್ತದೆ[।\.]*\s*ಮಳೆ ಬರುವ ಸಾಧ್ಯತೆ ಶೇಕಡಾ\s*([0-9.]+)\s*ಇದೆ[।\.]*\s*ಗಾಳಿಯಲ್ಲಿ ತೇವಾಂಶ ಶೇಕಡಾ\s*([0-9.]+)\s*ಇರುತ್ತದೆ[।\.]*(.*)/i,
    romanized: (m) => `Namaskara ${m[1].trim()} avare. Naanu Agrythm ninda havamana thilisalu kare maaduttiddene. Indu ${m[2].trim()} pradeshada havamana mahithi idu. Tapamana ${m[3].trim()} rinda ${m[4].trim()} degree naduve iruttade. Galiya vega gantege ${m[5].trim()} km varage iruttade. Male baruva sadhyate shekada ${m[6].trim()} ide. Galiyalli tevamsha shekada ${m[7].trim()} iruttade.`,
    translated: (m) => `Hello ${m[1].trim()}. I am calling from Agrythm to share the weather update. Today's forecast for ${m[2].trim()}: Temperature between ${m[3].trim()} and ${m[4].trim()}°C. Wind speed up to ${m[5].trim()} km/h. Rain chance is ${m[6].trim()}%, and humidity is ${m[7].trim()}%.`
  },
  // 3. HINDI GREETING (Orchestrator variant)
  {
    regex: /नमस्ते\s+([^,]+),\s*यह एग्रिद्म कनेक्ट से\s+([^क]+)के लिए आपका दैनिक मौसम समाचार है[।\.]*\s*आज का तापमान\s*([0-9.]+)[°\s]*C\s*और नमी\s*([0-9.]+)%\s*रहेगी[।\.]*\s*हवा की गति\s*([0-9.]+)\s*किमी\/घंटा\s*और बारिश की संभावना\s*([0-9.]+)%\s*है[।\.]*\s*क्या आप आज के मौसम के बारे में कुछ पूछना चाहते हैं\?/i,
    romanized: (m) => `Namaste ${m[1].trim()}, yeh Agrythm Connect se ${m[2].trim()} ke liye aapka dainik mausam samachar hai. Aaj ka tapman ${m[3].trim()}°C aur nami ${m[4].trim()}% rahegi. Hawa ki gati ${m[5].trim()} km/h aur barish ki sambhavna ${m[6].trim()}% hai. Kya aap aaj ke mausam ke baare mein kuch poochna chahte hain?`,
    translated: (m) => `Hello ${m[1].trim()}, this is your Agrythm Connect daily weather bulletin for ${m[2].trim()}. Today's temperature will be ${m[3].trim()}°C and humidity ${m[4].trim()}%. Wind speed will be ${m[5].trim()} km/h and rain probability is ${m[6].trim()}%. Do you have any questions about today's weather?`
  },
  // 4. HINDI GREETING (Weathercall script variant)
  {
    regex: /नमस्ते\s+([^\s]+)\s+जी[।\.]*\s*मैं एग्रिदम की ओर से मौसम बताने के लिए फ़ोन कर रही हूँ[।\.]*\s*आज\s+([^\s]+)\s+इलाके के मौसम की जानकारी यह है[।\.]*\s*तापमान\s*([0-9.]+)\s*से\s*([0-9.]+)\s*डिग्री के बीच रहेगा[।\.]*\s*हवा की रफ़्तार\s*([0-9.]+)\s*किलोमीटर प्रति घंटा तक रहेगी[।\.]*\s*बारिश होने की संभावना\s*([0-9.]+)\s*प्रतिशत है[।\.]*\s*हवा में नमी\s*([0-9.]+)\s*प्रतिशत रहेगी[।\.]*(.*)/i,
    romanized: (m) => `Namaste ${m[1].trim()} ji. Main Agrythm ki or se mausam batane ke liye phone kar rahi hoon. Aaj ${m[2].trim()} ilaake ke mausam ki jaankari yeh hai. Tapman ${m[3].trim()} se ${m[4].trim()} degree ke beech rahega. Hawa ki raftaar ${m[5].trim()} km/h tak rahegi. Barish hone ki sambhavna ${m[6].trim()}% hai. Hawa mein nami ${m[7].trim()}% rahegi.`,
    translated: (m) => `Hello ${m[1].trim()}. I am calling on behalf of Agrythm to share the weather update. Today's weather for ${m[2].trim()}: Temperature between ${m[3].trim()} and ${m[4].trim()}°C. Wind speed up to ${m[5].trim()} km/h. Chance of rain is ${m[6].trim()}%, and humidity is ${m[7].trim()}%.`
  },
  // 5. TELUGU GREETING (Gate Zero PR #10 Telugu script)
  {
    regex: /నమస్కారం\s+([^\s]+)\s+గారు[।\.]*\s*నేను అగ్రిథమ్ నుండి వాతావరణ సమాచారం చెప్పడానికి ఫోన్ చేస్తున్నాను[।\.]*\s*ఈ రోజు\s+([^\s]+)\s+ప్రాంతం వాతావరణ సమాచారం ఇది[।\.]*\s*ఉష్ణోగ్రత\s*([0-9.]+)\s*నుండి\s*([0-9.]+)\s*డిగ్రీల మధ్య ఉంటుంది[।\.]*\s*గాలి వేగం గంటకు\s*([0-9.]+)\s*కిలోమీటర్ల వరకు ఉంటుంది[।\.]*\s*వర్షం పడే అవకాశం\s*([0-9.]+)\s*శాతం ఉంది[।\.]*\s*గాలిలో తేమ\s*([0-9.]+)\s*శాతం ఉంటుంది[।\.]*(.*)/i,
    romanized: (m) => `Namaskaram ${m[1].trim()} gaaru. Nenu Agrythm nundi vatavarana samacharam cheppadaniki phone chestunnanu. Ee roju ${m[2].trim()} prantham vatavarana samacharam idi. Ushnograta ${m[3].trim()} nundi ${m[4].trim()} degreela madhya untundi. Gaali vegam gantaku ${m[5].trim()} km varaku untundi. Varsham pade avakasam ${m[6].trim()}% undi. Gaalilo teva ${m[7].trim()}% untundi.`,
    translated: (m) => `Hello ${m[1].trim()}. I am calling from Agrythm to provide the daily weather update. Today's forecast for ${m[2].trim()}: Temperature between ${m[3].trim()} and ${m[4].trim()}°C. Wind speed up to ${m[5].trim()} km/h. Precipitation probability is ${m[6].trim()}%, and air humidity is ${m[7].trim()}%.`
  },
  // 6. SARVAM AGENT OPENING INTRO (SARVAM_SETUP.md)
  {
    regex: /Hello\s+([^.]+)\.\s*I am Chetan Dabke's assistant, calling on behalf of Agrythm to share a short weather update for ([^.]+)\.\s*Is this a good time to talk\?/i,
    romanized: (m) => `Hello ${m[1].trim()}. I am Chetan Dabke's assistant, calling on behalf of Agrythm to share a short weather update for ${m[2].trim()}. Is this a good time to talk?`,
    translated: (m) => `Hello ${m[1].trim()}. I am Chetan Dabke's assistant, calling on behalf of Agrythm to share a short weather update for ${m[2].trim()}. Is this a good time to talk?`
  },
  // 7. KANNADA WEATHER DOUBT
  {
    regex: /ಇಂದು ಮಧ್ಯಾಹ್ನ ಮಳೆ ಬರುತ್ತದೆಯೇ\?\s*ಹೊಲದಲ್ಲಿ ಕೆಲಸ ಮಾಡಬಹುದೇ\?/i,
    romanized: () => "Indu madhyahna male baruttadeye? Holadalli kelasa madabahude?",
    translated: () => "Will it rain this afternoon? Can we work in the field?"
  },
  // 8. HINDI WEATHER DOUBT
  {
    regex: /क्या आज दोपहर बारिश होगी\?\s*हम खेत में काम कर सकते हैं\?/i,
    romanized: () => "Kya aaj dopahar barish hogi? Hum khet mein kaam kar sakte hain?",
    translated: () => "Will it rain this afternoon? Can we work in the field?"
  },
  // 9. TELUGU WEATHER DOUBT
  {
    regex: /ఈ రోజు వర్షం పడుతుందా\?\s*పొలంలో పని చేసుకోవచ్చా\?/i,
    romanized: () => "Ee roju varsham padutunda? Polamlo pani chesukovachha?",
    translated: () => "Will it rain today? Can we carry out work in the fields?"
  },
  // 10. KANNADA CALLBACK REQUEST
  {
    regex: /ಈಗ ಮಾರುಕಟ್ಟೆಯಲ್ಲಿದ್ದೇನೆ,?\s*ಸಂಜೆ\s*([0-9]+)\s*ಗಂಟೆಗೆ\s*(?:ಕರೆ|ಕಾಲ್)\s*ಮಾಡಿ[।\.]*/i,
    romanized: (m) => `Eega marukatteyalliddene, sanje ${m[1]} gantegae call madi.`,
    translated: (m) => `I am in the market right now, please call me back in the evening at ${m[1]} PM.`
  },
  // 11. HINDI CALLBACK REQUEST
  {
    regex: /शाम को\s*([0-9]+)\s*बजे कॉल करो,?\s*(?:अभी मंडी में व्यस्त हूँ|व्यस्त हूँ)[।\.]*/i,
    romanized: (m) => `Shaam ko ${m[1]} baje call karo, abhi mandi mein vyast hoon.`,
    translated: (m) => `Please call back in the evening at ${m[1]} PM, I am busy in the market right now.`
  },
  // 12. TELUGU CALLBACK REQUEST
  {
    regex: /ఇప్పుడు సంతలో ఉన్నాను,?\s*సాయంత్రం\s*([0-9]+)\s*గంటలకు ఫోన్ చేయండి[।\.]*/i,
    romanized: (m) => `Ippudu santalo unnanu, sayantram ${m[1]} gantalaku phone cheyandi.`,
    translated: (m) => `I am at the local market right now, please call back in the evening at ${m[1]} PM.`
  },
  // 13. KANNADA WEATHER DELIVERED RESPONSE
  {
    regex: /ಇಂದು ನಿಮ್ಮ ಪ್ರದೇಶದ ಹವಾಮಾನ:\s*ತಾಪಮಾನ\s*([0-9.]+)[°\s]*C,\s*ಗಾಳಿಯ ವೇಗ\s*(?:ಗಂಟೆಗೆ\s*)?([0-9.]+)\s*ಕಿಮೀ(?:\/ಗಂಟೆ)?,\s*ಮಳೆಯ ಸಾಧ್ಯತೆ\s*([0-9.]+)%\s*ಮತ್ತು ತೇವಾಂಶ\s*([0-9.]+)%\s*ಇದೆ[।\.]*/i,
    romanized: (m) => `Indu nimma pradeshada havamana: tapamana ${m[1]}°C, galiya vega ${m[2]} km/h, maleya sadhyate ${m[3]}% mattu tevamsha ${m[4]}% ide.`,
    translated: (m) => `Today's weather for your area: temperature is ${m[1]}°C, wind speed is ${m[2]} km/h, precipitation probability is ${m[3]}%, and humidity is ${m[4]}%.`
  },
  // 14. HINDI WEATHER DELIVERED RESPONSE
  {
    regex: /आज आपके इलाके का मौसम:\s*तापमान\s*([0-9.]+)[°\s]*C,\s*हवा की गति\s*([0-9.]+)\s*किमी\/घंटा,\s*बारिश की संभावना\s*([0-9.]+)%\s*और नमी\s*([0-9.]+)%\s*है[।\.]*\s*(.*)/i,
    romanized: (m) => `Aaj aapke ilaake ka mausam: tapman ${m[1]}°C, hawa ki gati ${m[2]} km/h, barish ki sambhavna ${m[3]}% aur nami ${m[4]}% hai. ${m[5]?.includes('सामान्य') ? 'Mausam samanya rahega.' : (m[5]?.includes('आसार') ? 'Barish ke aasaar hain, dhyan rakhein.' : '')}`.trim(),
    translated: (m) => `Today's weather for your area: temperature is ${m[1]}°C, wind speed is ${m[2]} km/h, rain chance is ${m[3]}%, and humidity is ${m[4]}%. ${m[5]?.includes('सामान्य') ? 'Conditions will remain normal.' : (m[5]?.includes('आसार') ? 'Rain is expected, please plan accordingly.' : '')}`.trim()
  },
  // 15. KANNADA CALLBACK CONFIRMATION
  {
    regex: /ಖಂಡಿತ[।\.]*\s*ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು ದಾಖಲಿಸಿಕೊಳ್ಳಲಾಗಿದೆ ಮತ್ತು\s*(.+?)\s*ಕ್ಕೆ ಕಾಲ್‌ಬ್ಯಾಕ್ ನಿಗದಿಪಡಿಸಲಾಗಿದೆ[।\.]*\s*ಧನ್ಯವಾದಗಳು[।\.]*/i,
    romanized: (m) => `Khandita. Nimma vinantiyannu dakhalisikollalagide mattu ${m[1]} kke callback nigadipadisalagide. Dhanyavadagalu.`,
    translated: (m) => `Certainly. Your request has been recorded and an automated callback is scheduled for ${m[1]}. Thank you.`
  },
  // 16. HINDI CALLBACK CONFIRMATION
  {
    regex: /समझ गया[।\.]*\s*हमने आपका समय नोट कर लिया है और\s*(.+?)\s*पर दोबारा कॉलबैक शेड्यूल किया है[।\.]*\s*धन्यवाद[।\.]*/i,
    romanized: (m) => `Samajh gaya. Humne aapka samay note kar liya hai aur ${m[1]} par dobara callback schedule kiya hai. Dhanyavaad.`,
    translated: (m) => `Understood. We have noted your preferred time and scheduled a callback for ${m[1]}. Thank you.`
  },
  // 17. KANNADA AGRONOMIC ESCALATION
  {
    regex: /ಬೆಳೆಗೆ ಕೀಟ ಬಾಧೆ ತಗುಲಿದೆ,?\s*ಯಾವ ಕೀಟನಾಶಕ ಔಷಧಿ ಸಿಂಪಡಿಸಬೇಕು\?/i,
    romanized: () => "Belege keeta baadhe tagulide, yaava keetanashaka aushadhi simpadisabeku?",
    translated: () => "My crop is suffering from pest damage, which pesticide should I spray?"
  },
  {
    regex: /ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್ ಕೇವಲ ಹವಾಮಾನ ಮುನ್ಸೂಚನೆಯನ್ನು ಮಾತ್ರ ಒದಗಿಸುತ್ತದೆ,?\s*ಕೃಷಿ ರಾಸಾಯನಿಕ ಸಲಹೆಯನ್ನಲ್ಲ[।\.]*\s*ನಿಮ್ಮ ವಿಚಾರಣೆಯನ್ನು ನಮ್ಮ ಕೃಷಿ ತಜ್ಞರಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ,?\s*ಅವರು ಶೀಘ್ರದಲ್ಲೇ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುತ್ತಾರೆ[।\.]*/i,
    romanized: () => "Agrythm Connect kevala havamana munsuchaneyannu maatra odagisuttade, krishi rasayanika salaheyannalla. Nimma vicharaneyannu namma krishi thajnjarige kaluhisalagide, avaru sheeghradalle nimmannu samparkisuttare.",
    translated: () => "Agrythm Connect provides only meteorological advisories, not chemical or crop advice. Your inquiry has been forwarded to our agricultural experts who will contact you shortly."
  },
  // 18. HINDI AGRONOMIC ESCALATION
  {
    regex: /फसल में कीड़ा लगा है,?\s*कौन सी कीटनाशक दवाई डालना चाहिए\?/i,
    romanized: () => "Fasal mein keeda laga hai, kaun si keetnashak dawai daalna chahiye?",
    translated: () => "My crop has pest infestation, which insecticide medicine should be applied?"
  },
  {
    regex: /एग्रिद्म कनेक्ट मौसम सहायक केवल मौसम की जानकारी दे सकता है,?\s*कीटनाशक या कृषि सलाह नहीं[।\.]*\s*आपका सवाल हमारे कृषि विशेषज्ञ को भेज दिया गया है,?\s*वे जल्द ही आपसे संपर्क करेंगे[।\.]*/i,
    romanized: () => "Agrythm Connect mausam sahayak keval mausam ki jaankari de sakta hai, keetnashak ya krishi salah nahi. Aapka sawal hamare krishi visheshagya ko bhej diya gaya hai, ve jald hi aapse sampark karenge.",
    translated: () => "Agrythm Connect Weather Assistant only provides meteorological advisories, not pesticide or farming advice. Your query has been forwarded to our agricultural specialist, who will contact you soon."
  }
];

// Helper: Checks if text has Indic script characters
export function hasIndicScript(text) {
  if (!text || typeof text !== 'string') return false;
  // Devanagari (0900-097F), Kannada (0C80-0CFF), Telugu (0C00-0C7F)
  return /[\u0900-\u097F\u0C80-\u0CFF\u0C00-\u0C7F]/.test(text);
}

/**
 * Phonetic transliterator mapping Indic characters (Kannada, Devanagari, Telugu) to Latin characters
 */
function transliterateIndicCharacters(text) {
  if (!text) return '';

  // Devanagari maps
  const devVowels = {
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo', 'ऋ': 'ri',
    'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'अं': 'am', 'अः': 'ah'
  };
  const devMatras = {
    'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo', 'ृ': 'ri',
    'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au'
  };
  const devConsonants = {
    'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
    'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
    'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v',
    'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h', 'क़': 'q', 'ख़': 'kh', 'ग़': 'gh', 'ज़': 'z', 'फ़': 'f'
  };

  // Kannada maps
  const kanVowels = {
    'ಅ': 'a', 'ಆ': 'aa', 'ಇ': 'i', 'ಈ': 'ee', 'ಉ': 'u', 'ಊ': 'oo', 'ಋ': 'ru',
    'ಎ': 'e', 'ಏ': 'ee', 'ಐ': 'ai', 'ಒ': 'o', 'ಓ': 'oo', 'ಔ': 'au', 'ಅಂ': 'am', 'ಅಃ': 'aha'
  };
  const kanMatras = {
    'ಾ': 'aa', 'ಿ': 'i', 'ೀ': 'ee', 'ು': 'u', 'ೂ': 'oo', 'ೃ': 'ru',
    'ೆ': 'e', 'ೇ': 'ee', 'ೈ': 'ai', 'ೊ': 'o', 'ೋ': 'oo', 'ೌ': 'au'
  };
  const kanConsonants = {
    'ಕ': 'k', 'ಖ': 'kh', 'ಗ': 'g', 'ಘ': 'gh', 'ಙ': 'ng',
    'ಚ': 'ch', 'ಛ': 'chh', 'ಜ': 'j', 'ಝ': 'jh', 'ಞ': 'ny',
    'ಟ': 't', 'ಠ': 'th', 'ಡ': 'd', 'ಢ': 'dh', 'ಣ': 'n',
    'ತ': 't', 'ಥ': 'th', 'ದ': 'd', 'ಧ': 'dh', 'ನ': 'n',
    'ಪ': 'p', 'ಫ': 'ph', 'ಬ': 'b', 'ಭ': 'bh', 'ಮ': 'm',
    'ಯ': 'y', 'ರ': 'r', 'ಱ': 'r', 'ಲ': 'l', 'ವ': 'v',
    'ಶ': 'sh', 'ಷ': 'sh', 'ಸ': 's', 'ಹ': 'h', 'ಳ': 'l', 'ೞ': 'l'
  };

  // Telugu maps
  const telVowels = {
    'అ': 'a', 'ఆ': 'aa', 'ఇ': 'i', 'ఈ': 'ee', 'ఉ': 'u', 'ఊ': 'oo', 'ఋ': 'ru',
    'ఎ': 'e', 'ఏ': 'ee', 'ఐ': 'ai', 'ఒ': 'o', 'ఓ': 'oo', 'ఔ': 'au', 'అం': 'am', 'అః': 'aha'
  };
  const telMatras = {
    'ా': 'aa', 'ి': 'i', 'ీ': 'ee', 'ు': 'u', 'ూ': 'oo', 'ృ': 'ru',
    'ె': 'e', 'ే': 'ee', 'ై': 'ai', 'ొ': 'o', 'ో': 'oo', 'ౌ': 'au'
  };
  const telConsonants = {
    'క': 'k', 'ఖ': 'kh', 'గ': 'g', 'ఘ': 'gh', 'ఙ': 'ng',
    'చ': 'ch', 'ఛ': 'chh', 'జ': 'j', 'ఝ': 'jh', 'ఞ': 'ny',
    'ట': 't', 'ఠ': 'th', 'డ': 'd', 'ఢ': 'dh', 'ణ': 'n',
    'త': 't', 'థ': 'th', 'ద': 'd', 'ధ': 'dh', 'న': 'n',
    'ప': 'p', 'ఫ': 'ph', 'బ': 'b', 'భ': 'bh', 'మ': 'm',
    'య': 'y', 'ర': 'r', 'ల': 'l', 'వ': 'v',
    'శ': 'sh', 'ష': 'sh', 'స': 's', 'హ': 'h', 'ళ': 'l'
  };

  // Indic symbols: anusvara, visarga, danda
  const indicSymbols = {
    'ं': 'n', 'ँ': 'n', 'ः': 'h',
    'ಂ': 'm', 'ಃ': 'h',
    'ం': 'm', 'ః': 'h',
    '।': '.', '॥': '.'
  };

  let out = '';
  const len = text.length;

  for (let i = 0; i < len; i++) {
    const ch = text[i];
    const next = i + 1 < len ? text[i + 1] : '';

    // Check independent vowels
    if (devVowels[ch]) {
      out += devVowels[ch];
      continue;
    }
    if (kanVowels[ch]) {
      out += kanVowels[ch];
      continue;
    }
    if (telVowels[ch]) {
      out += telVowels[ch];
      continue;
    }

    // Check symbols (anusvara, visarga, danda)
    if (indicSymbols[ch]) {
      out += indicSymbols[ch];
      continue;
    }

    // Check consonants
    if (devConsonants[ch]) {
      const base = devConsonants[ch];
      if (next === '\u094D') {
        // Halant (virama) -> suppresses inherent vowel
        out += base;
        i++; // skip virama
      } else if (devMatras[next]) {
        out += base + devMatras[next];
        i++; // skip matra
      } else if (i === len - 1 || /[\s,.\-!?]/.test(next)) {
        out += base;
      } else {
        out += base + 'a';
      }
      continue;
    }

    if (kanConsonants[ch]) {
      const base = kanConsonants[ch];
      if (next === '\u0C4D') {
        // Virama -> suppresses inherent vowel
        out += base;
        i++; // skip virama
      } else if (kanMatras[next]) {
        out += base + kanMatras[next];
        i++; // skip matra
      } else if (i === len - 1 || /[\s,.\-!?]/.test(next)) {
        out += base;
      } else {
        out += base + 'a';
      }
      continue;
    }

    if (telConsonants[ch]) {
      const base = telConsonants[ch];
      if (next === '\u0C4D') {
        // Telugu virama -> suppresses inherent vowel
        out += base;
        i++;
      } else if (telMatras[next]) {
        out += base + telMatras[next];
        i++;
      } else if (i === len - 1 || /[\s,.\-!?]/.test(next)) {
        out += base;
      } else {
        out += base + 'a';
      }
      continue;
    }

    // Punctuation danda
    if (ch === '।') {
      out += '.';
      continue;
    }

    out += ch;
  }

  return out;
}

/**
 * Returns text converted to English Script (Romanized / Same Spoken Language)
 * e.g. "ನಮಸ್ಕಾರ Harshith" -> "Namaskara Harshith"
 */
export function getRomanizedTranscript(text) {
  if (!text || typeof text !== 'string') return '';
  const trimmed = text.trim();

  // 1. Try phrase matchers for high-fidelity idiomatic transliterations
  for (const item of PHRASE_PATTERNS) {
    const match = trimmed.match(item.regex);
    if (match) {
      return item.romanized(match);
    }
  }

  // 2. Fall back to character-level transliterator if Indic script is present
  if (hasIndicScript(trimmed)) {
    return transliterateIndicCharacters(trimmed);
  }

  return trimmed;
}

/**
 * Returns text translated to English
 * e.g. "ನಮಸ್ಕಾರ Harshith..." -> "Hello Harshith, this is today's weather forecast..."
 */
export function getTranslatedTranscript(text) {
  if (!text || typeof text !== 'string') return '';
  const trimmed = text.trim();

  // 1. Try phrase matchers for high-fidelity English translations
  for (const item of PHRASE_PATTERNS) {
    const match = trimmed.match(item.regex);
    if (match) {
      return item.translated(match);
    }
  }

  // 2. If it is already in English, return as is
  if (!hasIndicScript(trimmed)) {
    return trimmed;
  }

  // 3. Fallback: Romanize if an exact translation isn't available
  return transliterateIndicCharacters(trimmed);
}

/**
 * Formats transcript turn text according to selected mode:
 * - 'romanized': English script, same language (Default)
 * - 'translated': Translated into English
 * - 'original': Native script (Kannada / Hindi / Telugu)
 */
export function formatTranscriptText(text, mode = 'romanized') {
  if (!text) return '';
  switch (mode) {
    case 'translated':
      return getTranslatedTranscript(text);
    case 'original':
      return text;
    case 'romanized':
    default:
      return getRomanizedTranscript(text);
  }
}
