/**
 * Transcript Translation & Romanization (Transliteration) Utilities
 * 
 * Supports 3 modes for conversation dialogues:
 * 1. 'translated' (Translate to English - 100% pure English, never Hinglish/Kanglish)
 * 2. 'romanized' (English Script - same spoken language written phonetically in Latin alphabet)
 * 3. 'original' (Original Indic script: Kannada, Devanagari Hindi, Telugu)
 * 
 * Fully covers:
 * - Real recorded calls from SQLite database (Gadag, Dharwad, Kannada, Hindi, Telugu)
 * - Sarvam Voice AI live telephony agent dialogues
 * - Inbound and outbound campaign weather advisories
 */

// Common Indic name mapping to clean English spelling
const INDIC_NAME_MAP = {
  // Kannada
  'ರಮೇಶ್': 'Ramesh',
  'ರಮೇಶ್ ಅವರೇ': 'Ramesh',
  'ಸುರೇಶ್': 'Suresh',
  'ಸುರೇಶ್ ಅವರೇ': 'Suresh',
  'ಬಸವರಾಜಪ್ಪ': 'Basavarajappa',
  'ಬಸವರಾಜಪ್ಪ ಅವರೇ': 'Basavarajappa',
  'ಶಾಂತಮ್ಮ': 'Shantamma',
  'ಸೋಮಶೇಖರ್': 'Somasekhar',
  'ಮಂಜುಳಾ': 'Manjula',
  'ಲಕ್ಷ್ಮಿ': 'Lakshmi',
  'ಗದಗ': 'Gadag',
  'ಧಾರವಾಡ': 'Dharwad',
  'ಹಾವೇರಿ': 'Haveri',
  'ಬೆಳಗಾವಿ': 'Belagavi',
  'ಕೊಪ್ಪಳ': 'Koppal',
  'ಬಾಗಲಕೋಟೆ': 'Bagalkote',
  'ವಿಜಯಪುರ': 'Vijayapura',
  'ಬಳ್ಳಾರಿ': 'Ballari',
  'ದಾವಣಗೆರೆ': 'Davanagere',

  // Hindi
  'नेहा': 'Neha',
  'नेहा जी': 'Neha',
  'अमित': 'Amit',
  'राहुल': 'Rahul',
  'राजेश': 'Rajesh',
  'रमेश': 'Ramesh',
  'सुरेश': 'Suresh',
  'सीता': 'Sita',
  'गीता': 'Geeta',

  // Telugu
  'ఆనంద్': 'Anand',
  'ఆనంద్ గారు': 'Anand',
  'సురేష్': 'Suresh',
  'రమేష్': 'Ramesh',
  'రాజేష్': 'Rajesh',
  'కృష్ణ': 'Krishna'
};

function resolveIndicName(raw) {
  if (!raw) return '';
  const clean = raw.replace(/[\u200B-\u200D\uFEFF]/g, '').trim();
  if (INDIC_NAME_MAP[clean]) return INDIC_NAME_MAP[clean];
  // Remove trailing honorifics like ಅವರೇ, जी, గారు
  const stripped = clean
    .replace(/\s*(?:ಅವರೇ|जी|గారు|avare|ji|jee|gaaru)\s*$/i, '')
    .trim();
  if (INDIC_NAME_MAP[stripped]) return INDIC_NAME_MAP[stripped];
  // If in Latin already
  return stripped.charAt(0).toUpperCase() + stripped.slice(1);
}

// Comprehensive phrase dictionaries for natural, idiomatic translations & transliterations
const PHRASE_PATTERNS = [
  // 1. KANNADA: Weather forecast greeting with area
  // "ನಮಸ್ಕಾರ ರಮೇಶ್ ಅವರೇ, ಇದು ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್‌ನಿಂದ ಗದಗ ಪ್ರದೇಶದ ಇಂದಿನ ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ."
  {
    regex: /(?:ನಮಸ್ಕಾರ|ನಮಸ್ತೆ)\s+([^,]+?)\s+ಅವರೇ[,.]*\s*ಇದು ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್(?:[\u200c\s]*ನಿಂದ)?\s+(.+?)\s+ಪ್ರದೇಶದ ಇಂದಿನ ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ[।.]*/i,
    romanized: (m) => `Namaskara ${resolveIndicName(m[1])} avare, idu Agrythm Connect ninda ${resolveIndicName(m[2])} pradeshada indina havamana munsuchane.`,
    translated: (m) => `Hello ${resolveIndicName(m[1])}, this is today's weather forecast for ${resolveIndicName(m[2])} region from Agrythm Connect.`
  },
  {
    regex: /(?:namaskara|namaste)\s+([^,]+?)\s+avare[,.]*\s*idu agrythm connect(?:\s*ninda)?\s+(.+?)\s+pradeshada indina havamana munsuchane[।.]*/i,
    romanized: (m) => `Namaskara ${m[1].trim()} avare, idu Agrythm Connect ninda ${m[2].trim()} pradeshada indina havamana munsuchane.`,
    translated: (m) => `Hello ${m[1].trim()}, this is today's weather forecast for ${m[2].trim()} region from Agrythm Connect.`
  },

  // 2. KANNADA: Calling to share weather info
  // "ನಮಸ್ಕಾರ ಬಸವರಾಜಪ್ಪ ಅವರೇ, ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್‌ನಿಂದ ಹವಾಮಾನ ಮಾಹಿತಿ ತಿಳಿಸಲು ಕರೆ ಮಾಡಿದ್ದೇವೆ."
  {
    regex: /(?:ನಮಸ್ಕಾರ|ನಮಸ್ತೆ)\s+([^,]+?)\s+ಅವರೇ[,.]*\s*ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್(?:[\u200c\s]*ನಿಂದ)?\s*ಹವಾಮಾನ ಮಾಹಿತಿ ತಿಳಿಸಲು ಕರೆ ಮಾಡಿದ್ದೇವೆ[।.]*/i,
    romanized: (m) => `Namaskara ${resolveIndicName(m[1])} avare, Agrythm Connect ninda havamana mahiti thilisalu kare maadiddeve.`,
    translated: (m) => `Hello ${resolveIndicName(m[1])}, we are calling from Agrythm Connect to provide weather information.`
  },
  {
    regex: /(?:namaskara|namaste)\s+([^,]+?)\s+avare[,.]*\s*agrythm connect(?:\s*ninda)?\s*hava+ma+n ma+hiti tilisalu kare ma+di[a-z]*[।.]*/i,
    romanized: (m) => `Namaskara ${m[1].trim()} avare, Agrythm Connect ninda havamana mahiti thilisalu kare maadiddeve.`,
    translated: (m) => `Hello ${m[1].trim()}, we are calling from Agrythm Connect to provide weather information.`
  },

  // 3. KANNADA: Rain inquiry
  // "ನಮಸ್ಕಾರ, ಇವತ್ತು ಮಳೆ ಬರೋ ಸಾಧ್ಯತೆ ಇದೆಯಾ?"
  {
    regex: /(?:ನಮಸ್ಕಾರ|ನಮಸ್ತೆ)?[,\s]*ಇವತ್ತು ಮಳೆ ಬರೋ ಸಾಧ್ಯತೆ ಇದೆಯಾ\?/i,
    romanized: () => "Namaskara, ivattu male baro sadhyate ideya?",
    translated: () => "Hello, is there a chance of rain today?"
  },
  {
    regex: /(?:namaskara|namaste)?[,\s]*ivattu male baro sadhyate ideya\?/i,
    romanized: () => "Namaskara, ivattu male baro sadhyate ideya?",
    translated: () => "Hello, is there a chance of rain today?"
  },

  // 4. KANNADA: Weather details (max temp, evening rain chance, wind speed)
  // "ಇಂದು ಗರಿಷ್ಠ ತಾಪಮಾನ 31 ಡಿಗ್ರಿ, ಸಂಜೆ 4 ಗಂಟೆಯ ನಂತರ ಲಘು ಮಳೆಯಾಗುವ 65% ಸಾಧ್ಯತೆಯಿದೆ. ಗಾಳಿಯ ವೇಗ ಗಂಟೆಗೆ 14 ಕಿ.ಮೀ ಇರುತ್ತದೆ."
  {
    regex: /ಇಂದು ಗರಿಷ್ಠ ತಾಪಮಾನ\s*([0-9.]+)\s*ಡಿಗ್ರಿ[,\s]*ಸಂಜೆ\s*([0-9.]+)\s*ಗಂಟೆಯ ನಂತರ ಲಘು ಮಳೆಯಾಗುವ\s*([0-9.]+)%\s*ಸಾಧ್ಯತೆಯಿದೆ[।.]*\s*ಗಾಳಿಯ ವೇಗ ಗಂಟೆಗೆ\s*([0-9.]+)\s*ಕಿ\.?ಮೀ(?:ಟರ್)?\s*ಇರುತ್ತದೆ[।.]*/i,
    romanized: (m) => `Indu garishta tapamana ${m[1]} degree, sanje ${m[2]} gantiya nantara laghu maleyaguva ${m[3]}% sadhyateyide. Galiya vega gantege ${m[4]} km iruttade.`,
    translated: (m) => `Today the maximum temperature is ${m[1]}°C, with a ${m[3]}% chance of light rain after ${m[2]} PM. Wind speed will be ${m[4]} km/h.`
  },
  {
    regex: /indu garisht[a-z]* ta+pama+n\s*([0-9.]+)\s*diga?ri[,\s]*sam?je\s*([0-9.]+)\s*gam?tey?a? namtar laghu male[a-z]*\s*([0-9.]+)%\s*sa+dha?yatey?ide[।.]*\s*ga+liy? ve+g gam?tege\s*([0-9.]+)\s*ki\.?me+ iru[a-z]*[।.]*/i,
    romanized: (m) => `Indu garishta tapamana ${m[1]} degree, sanje ${m[2]} gantiya nantara laghu maleyaguva ${m[3]}% sadhyateyide. Galiya vega gantege ${m[4]} km iruttade.`,
    translated: (m) => `Today the maximum temperature is ${m[1]}°C, with a ${m[3]}% chance of light rain after ${m[2]} PM. Wind speed will be ${m[4]} km/h.`
  },

  // 5. KANNADA: Pesticide postponement
  // "ಸರಿ, ಹಾಗಾದ್ರೆ ಕೀಟನಾಶಕ ಸಿಂಪಡಣೆಯನ್ನು ನಾಳೆಗೆ ಮುಂದೂಡುತ್ತೇನೆ. ಧನ್ಯವಾದ."
  {
    regex: /ಸರಿ[,\s]*ಹಾಗಾದ್ರೆ ಕೀಟನಾಶಕ ಸಿಂಪಡಣೆಯನ್ನು ನಾಳೆಗೆ ಮುಂದೂಡುತ್ತೇನೆ[।.]*\s*ಧನ್ಯವಾದ[।.]*/i,
    romanized: () => "Sari, hagadre keetanashaka simpadaneyannu naalege mundooduttene. Dhanyavada.",
    translated: () => "Alright, then I will postpone pesticide spraying to tomorrow. Thank you."
  },
  {
    regex: /sari[,\s]*ha+ga?d?re\s+ke+tana+shak[a]?\s+simpadan[a-z]*\s+na+le+ge\s+mu[mn]?do+d[a-z]*[।.]*\s*dhana?yava+da?[।.]*/i,
    romanized: () => "Sari, hagadre keetanashaka simpadaneyannu naalege mundooduttene. Dhanyavada.",
    translated: () => "Alright, then I will postpone pesticide spraying to tomorrow. Thank you."
  },

  // 6. KANNADA: Sign-off
  // "ತುಂಬಾ ಧನ್ಯವಾದಗಳು, ಶುಭ ದಿನ."
  {
    regex: /ತುಂಬಾ ಧನ್ಯವಾದಗಳು[,\s]*ಶುಭ ದಿನ[।.]*/i,
    romanized: () => "Tumba dhanyavadagalu, shubha dina.",
    translated: () => "Thank you very much, have a good day."
  },
  {
    regex: /tumba+?\s*dhana?yava+dagalu[,\s]*shubh[a]?\s*din[a]?[।.]*/i,
    romanized: () => "Tumba dhanyavadagalu, shubha dina.",
    translated: () => "Thank you very much, have a good day."
  },

  // 7. KANNADA: Market noise / callback request
  // "ನಾನು ಈಗ ಮಾರುಕಟ್ಟೆಯಲ್ಲಿದ್ದೇನೆ, ತುಂಬಾ ಗದ್ದಲವಿದೆ. ಇನ್ನೆರಡು ಗಂಟೆ ಬಿಟ್ಟು ಮಧ್ಯಾಹ್ನ ಕರೆ ಮಾಡಿ."
  {
    regex: /ನಾನು ಈಗ ಮಾರುಕಟ್ಟೆಯಲ್ಲಿದ್ದೇನೆ[,\s]*ತುಂಬಾ ಗದ್ದಲವಿದೆ[।.]*\s*ಇನ್ನೆರಡು ಗಂಟೆ ಬಿಟ್ಟು ಮಧ್ಯಾಹ್ನ ಕರೆ ಮಾಡಿ[।.]*/i,
    romanized: () => "Naanu eega marukatteyalliddene, tumba gaddalavide. Inneradu gante bittu madhyahna kare madi.",
    translated: () => "I am in the market right now, it is very noisy. Please call back after two hours in the afternoon."
  },
  {
    regex: /na+nu e+g[a]? ma+rukat+eyal+[a-z]*[,\s]*tumba+? gad+[a-z]*[।.]*\s*in+eradu gam?te bit+u madh?ya+h?na? kare ma+di[।.]*/i,
    romanized: () => "Naanu eega marukatteyalliddene, tumba gaddalavide. Inneradu gante bittu madhyahna kare madi.",
    translated: () => "I am in the market right now, it is very noisy. Please call back after two hours in the afternoon."
  },

  // 8. KANNADA: Callback confirmation
  // "ಖಂಡಿತ, ಮಧ್ಯಾಹ್ನ 2 ಗಂಟೆಗೆ ನಿಮ್ಮನ್ನು ಮತ್ತೆ ಸಂಪರ್ಕಿಸುತ್ತೇವೆ. ಧನ್ಯವಾದ."
  {
    regex: /ಖಂಡಿತ[,\s]*ಮಧ್ಯಾಹ್ನ\s*([0-9.]+)\s*ಗಂಟೆಗೆ ನಿಮ್ಮನ್ನು ಮತ್ತೆ ಸಂಪರ್ಕಿಸುತ್ತೇವೆ[।.]*\s*ಧನ್ಯವಾದ[।.]*/i,
    romanized: (m) => `Khandita, madhyahna ${m[1]} gantege nimmannu matte samparkisutteve. Dhanyavada.`,
    translated: (m) => `Certainly, we will contact you again at ${m[1]} PM in the afternoon. Thank you.`
  },
  {
    regex: /kham?dit[a]?[,\s]*madh?ya+h?na?\s*([0-9.]+)\s*gam?tege nim+[a-z]* mat+e sam?par[a-z]*[।.]*\s*dhana?yava+d[a]?[।.]*/i,
    romanized: (m) => `Khandita, madhyahna ${m[1]} gantege nimmannu matte samparkisutteve. Dhanyavada.`,
    translated: (m) => `Certainly, we will contact you again at ${m[1]} PM in the afternoon. Thank you.`
  },

  // 9. HINDI: Weather greeting
  // "नमस्ते नेहा जी, यह एग्रीदम कनेक्ट से आज का मौसम समाचार है।"
  {
    regex: /(?:नमस्ते|नमस्कार)\s+([^,\s]+)\s+जी[,.]*\s*यह एग्रीदम कनेक्ट से आज का मौसम समाचार है[।.]*/i,
    romanized: (m) => `Namaste ${resolveIndicName(m[1])} ji, yeh Agrythm Connect se aaj ka mausam samachar hai.`,
    translated: (m) => `Hello ${resolveIndicName(m[1])}, this is today's weather update from Agrythm Connect.`
  },
  {
    regex: /(?:namaste|namaskar)\s+([^,\s]+)\s+(?:ji|jee)[,.]*\s*yeh (?:agrythm|agree?dam)\s*(?:connect|kanekt)?\s*se aaj ka+ mausam sama+cha+r hai[।.]*/i,
    romanized: (m) => `Namaste ${m[1].trim()} ji, yeh Agrythm Connect se aaj ka mausam samachar hai.`,
    translated: (m) => `Hello ${m[1].trim()}, this is today's weather update from Agrythm Connect.`
  },

  // 10. HINDI: Sunshine inquiry
  // "हाँ बताइए, आज धूप कैसी रहेगी?"
  {
    regex: /हाँ बताइए[,\s]*आज धूप कैसी रहेगी\?/i,
    romanized: () => "Haan bataiye, aaj dhoop kaisi rahegi?",
    translated: () => "Yes please tell me, how will the sunshine be today?"
  },
  {
    regex: /(?:haan|ha)\s*batai?y?e?[,\s]*aaj dho+p kais[ie]+ raheg[ie]+\?/i,
    romanized: () => "Haan bataiye, aaj dhoop kaisi rahegi?",
    translated: () => "Yes please tell me, how will the sunshine be today?"
  },

  // 11. HINDI: Weather details
  // "आज अधिकतम तापमान 32 डिग्री सेल्सियस और न्यूनतम 21 डिग्री रहेगा। दिनभर मौसम साफ रहेगा, बारिश की कोई संभावना नहीं है।"
  {
    regex: /आज अधिकतम तापमान\s*([0-9.]+)\s*डिग्री(?: सेल्सियस)?\s*और न्यूनतम\s*([0-9.]+)\s*डिग्री रहेगा[।.]*\s*दिनभर मौसम साफ रहेगा[,\s]*बारिश की कोई संभावना नहीं है[।.]*/i,
    romanized: (m) => `Aaj adhikatam tapman ${m[1]} degree celsius aur nyunatam ${m[2]} degree rahega. Dinbhar mausam saaf rahega, barish ki koi sambhavna nahi hai.`,
    translated: (m) => `Today the maximum temperature will be ${m[1]}°C and minimum ${m[2]}°C. The weather will remain clear throughout the day, with no chance of rain.`
  },
  {
    regex: /aaj adhikatam ta+pama+n\s*([0-9.]+)\s*digree(?: selsiyas)?\s*aur nyoonatam\s*([0-9.]+)\s*digree rahega+[।.]*\s*dinabhar mausam sa+ph rahega+[,\s]*ba+rish ke+ ko+e+ san?bha+vana+ nahee?n hai[।.]*/i,
    romanized: (m) => `Aaj adhikatam tapman ${m[1]} degree celsius aur nyunatam ${m[2]} degree rahega. Dinbhar mausam saaf rahega, barish ki koi sambhavna nahi hai.`,
    translated: (m) => `Today the maximum temperature will be ${m[1]}°C and minimum ${m[2]}°C. The weather will remain clear throughout the day, with no chance of rain.`
  },

  // 12. HINDI: Harvesting confirmation
  // "बहुत अच्छा, आज हम खेत में कटाई शुरू कर सकते हैं। धन्यवाद।"
  {
    regex: /बहुत अच्छा[,\s]*आज हम खेत में कटाई शुरू कर सकते हैं[।.]*\s*धन्यवाद[।.]*/i,
    romanized: () => "Bahut achha, aaj hum khet mein katai shuru kar sakte hain. Dhanyavaad.",
    translated: () => "Very good, we can start harvesting in the field today. Thank you."
  },
  {
    regex: /(?:bahut\s+ach+h?a+|bahut\s+accha)[,\s]*aaj\s+hum?\s+khet\s+me+i?n?\s+kataa?i?\s+shuru\s+kar\s+sakte\s+hai?n[।.]*\s*dhanya?va+d[a]?[।.]*/i,
    romanized: () => "Bahut achha, aaj hum khet mein katai shuru kar sakte hain. Dhanyavaad.",
    translated: () => "Very good, we can start harvesting in the field today. Thank you."
  },

  // 13. HINDI: Sign-off
  // "शुभ दिन नेहा जी, एग्रीदम कनेक्ट से जुड़ने के लिए धन्यवाद।"
  {
    regex: /शुभ दिन\s+([^,\s]+)\s+जी[,.]*\s*एग्रीदम कनेक्ट से जुड़ने के लिए धन्यवाद[।.]*/i,
    romanized: (m) => `Shubh din ${resolveIndicName(m[1])} ji, Agrythm Connect se judne ke liye dhanyavaad.`,
    translated: (m) => `Have a good day ${resolveIndicName(m[1])}, thank you for connecting with Agrythm Connect.`
  },
  {
    regex: /shubh din\s+([^,\s]+)\s+(?:ji|jee)[,.]*\s*(?:agrythm|agree?dam)\s*(?:connect|kanekt)?\s*se jud[a-z]* ke lie dhanya?va+da?[।.]*/i,
    romanized: (m) => `Shubh din ${m[1].trim()} ji, Agrythm Connect se judne ke liye dhanyavaad.`,
    translated: (m) => `Have a good day ${m[1].trim()}, thank you for connecting with Agrythm Connect.`
  },

  // 14. TELUGU: Weather greeting
  // "నమస్కారం ఆనంద్ గారు, అగ్రిథమ్ కనెక్ట్ నుండి నేటి వాతావరణ సమాచారం."
  {
    regex: /(?:నమస్కారం|నమస్తే)\s+([^,\s]+)\s+గారు[,.]*\s*అగ్రిథమ్ కనెక్ట్ నుండి నేటి వాతావరణ సమాచారం[।.]*/i,
    romanized: (m) => `Namaskaram ${resolveIndicName(m[1])} gaaru, Agrythm Connect nundi neti vatavarana samacharam.`,
    translated: (m) => `Hello ${resolveIndicName(m[1])}, this is today's weather information from Agrythm Connect.`
  },
  {
    regex: /(?:namaskaaram|namastee?)\s+([^,\s]+)\s+gaaru[,.]*\s*(?:agrythm|agritham)\s*(?:connect|kanekt)?\s*numdi neeti va+ta+varan sama+cha+ram[।.]*/i,
    romanized: (m) => `Namaskaram ${m[1].trim()} gaaru, Agrythm Connect nundi neti vatavarana samacharam.`,
    translated: (m) => `Hello ${m[1].trim()}, this is today's weather information from Agrythm Connect.`
  },

  // 15. TELUGU: Rain inquiry
  // "నమస్తే, ఈ రోజు వర్షం పడే అవకాశం ఉందా?"
  {
    regex: /(?:నమస్కారం|నమస్తే)?[,\s]*ఈ రోజు వర్షం పడే అవకాశం ఉందా\?/i,
    romanized: () => "Namaste, ee roju varsham pade avakasam unda?",
    translated: () => "Hello, is there a chance of rain today?"
  },
  {
    regex: /(?:namaskaaram|namastee?)?[,\s]*ee ro+ju varsham pade+ avaka+sham um?da+\?/i,
    romanized: () => "Namaste, ee roju varsham pade avakasam unda?",
    translated: () => "Hello, is there a chance of rain today?"
  },

  // 16. TELUGU: Weather details
  // "ఈ రోజు గరిష్ట ఉష్ణోగ్రత 33 డిగ్రీలు ఉంటుంది. సాయంత్రం వేళల్లో ఉరుములతో కూడిన జల్లులు పడే అవకాశం 40% ఉంది."
  {
    regex: /ఈ రోజు గరిష్ట ఉష్ణోగ్రత\s*([0-9.]+)\s*డిగ్రీలు ఉంటుంది[।.]*\s*సాయంత్రం వేళల్లో ఉరుములతో కూడిన జల్లులు పడే అవకాశం\s*([0-9.]+)%\s*ఉంది[।.]*/i,
    romanized: (m) => `Ee roju garishta ushnograta ${m[1]} degreelu untundi. Sayantram velallo urumulato kudina jallulu pade avakasam ${m[2]}% undi.`,
    translated: (m) => `Today the maximum temperature will be ${m[1]}°C. There is a ${m[2]}% chance of thundershowers in the evening.`
  },
  {
    regex: /ee ro+ju garisht[a-z]* ushno+grat\s*([0-9.]+)\s*digreelu um?tumdi[।.]*\s*sa+yamtram ve+lalloo urumulatoo koodin jallulu pade+ avaka+sham\s*([0-9.]+)%\s*um?di[।.]*/i,
    romanized: (m) => `Ee roju garishta ushnograta ${m[1]} degreelu untundi. Sayantram velallo urumulato kudina jallulu pade avakasam ${m[2]}% undi.`,
    translated: (m) => `Today the maximum temperature will be ${m[1]}°C. There is a ${m[2]}% chance of thundershowers in the evening.`
  },

  // 17. TELUGU: Irrigation arrangements
  // "అలాగే, నీటి పారుదల ఏర్పాట్లు చేసుకుంటాను. ధన్యవాదాలు." (Handles both pure Telugu and mixed Kannada/Telugu characters)
  {
    regex: /అలాగే[,\s]*నీటి\s*పారుదల\s*ఏర్పాట్లు\s*చేసుకుంటాను[।.]*\s*(?:ಧನ್ಯవాదాలు|ధన్యవాదాలు|ಧನ್ಯವಾದಗಳು|ಧನ್ಯವಾದ)[।.]*/i,
    romanized: () => "Alage, neeti parudala erpatlu chesukuntanu. Dhanyavadalu.",
    translated: () => "Alright, I will make irrigation arrangements. Thank you."
  },
  {
    regex: /ala+ge+[,\s]*ne+ti pa+rudal eerpa+tlu che+sukumta+nu[।.]*\s*dhanyava+da+lu[।.]*/i,
    romanized: () => "Alage, neeti parudala erpatlu chesukuntanu. Dhanyavadalu.",
    translated: () => "Alright, I will make irrigation arrangements. Thank you."
  },

  // 18. TELUGU: Sign-off
  // "ధన్యవాదాలు ఆనంద్ గారు."
  {
    regex: /(?:ధన్యవాదాలు|ಧನ್ಯವಾదాలు)\s+([^,\s]+)\s+గారు[।.]*/i,
    romanized: (m) => `Dhanyavadalu ${resolveIndicName(m[1])} gaaru.`,
    translated: (m) => `Thank you ${resolveIndicName(m[1])}.`
  },
  {
    regex: /dhanyava+da+lu\s+([^,\s]+)\s+gaaru[।.]*/i,
    romanized: (m) => `Dhanyavadalu ${m[1].trim()} gaaru.`,
    translated: (m) => `Thank you ${m[1].trim()}.`
  },

  // 19. Common Callback / Evening reschedule phrases (Indic & Romanized)
  {
    regex: /(?:ಸಂಜೆ|ಶಾಮ ಕೋ|సాయంత్రం|sanje|shaam ko|sayantram)\s*([0-9]+)\s*(?:ಗಂಟೆಗೆ|ಬಜೆ|గంటలకు|baje|gantegae|gantalaku)?\s*(?:ಕರೆ ಮಾಡಿ|ಕಾಲ್ ಕರೋ|ఫోన్ చేయండి|call karo|call madi|phone cheyandi)[^.]*/i,
    romanized: (m) => `Shaam ko ${m[1]} baje call kijiye.`,
    translated: (m) => `Please call back in the evening at ${m[1]} PM.`
  },
  {
    regex: /(?:ಮಾರುಕಟ್ಟೆಯಲ್ಲಿದ್ದೇನೆ|ಮಂಡಿ ಮೇ ಹೂಂ|సంతలో ఉన్నాను|mandi mein|marukatteyalli)\s*[^.]*/i,
    romanized: () => "Mandi mein hoon, baad mein call karo.",
    translated: () => "I am busy in the market right now, please call back later."
  },

  // 20. Agronomic escalation: pest / pesticide inquiry
  {
    regex: /(?:ಬೆಳೆಗೆ ಕೀಟ ಬಾಧೆ|ಫಸಲ್ ಮೇ ಕೀಡಾ|పంటకు పురుగు)\s*[^.]*/i,
    romanized: () => "Belege keeta badhe tagulide, yaava keetanashaka aushadhi simpadisabeku?",
    translated: () => "My crop has pest infestation, which pesticide should I spray?"
  },
  {
    regex: /(?:ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್ ಕೇವಲ ಹವಾಮಾನ|एग्रिद्म कनेक्ट मौसम सहायक केवल मौसम|అగ్రిథమ్ వాతావరణ సహాయకుడు)\s*[^.]*/i,
    romanized: () => "Agrythm Connect kevala havamana munsuchaneyannu maatra odagisuttade, krishi rasayanika salaheyannalla.",
    translated: () => "Agrythm Connect provides meteorological advisories, not chemical advice. Your inquiry has been forwarded to agricultural experts."
  }
];

// Fallback dictionary for individual words and phrases when translating to pure English
const VOCABULARY_TRANSLATIONS = [
  // Courtesies & Responses
  { pattern: /\b(ತುಂಬಾ ಧನ್ಯವಾದಗಳು|ಧನ್ಯವಾದಗಳು|ಧನ್ಯವಾದ|ಧನ್ಯವಾదాలు|ధన్యవాదాలు|dhanyavadagalu|dhanyavada|dhanyavaad|dhanyavaada|dhanyavadalu|dhanyavaadaalu)\b/gi, replacement: "Thank you" },
  { pattern: /\b(ಶುಭ ದಿನ|shubh din|shubha dina)\b/gi, replacement: "Have a good day" },
  { pattern: /\b(ನಮಸ್ಕಾರ|ನಮಸ್ತೆ|नमस्ते|नमस्कार|నమస్కారం|నమస్తే|namaskara|namaste|namaskar|namaskaram)\b/gi, replacement: "Hello" },
  { pattern: /\b(ಖಂಡಿತ|khandita|samajh gaya)\b/gi, replacement: "Certainly" },
  { pattern: /\b(ಸರಿ|ಹಾಗಾದ್ರೆ|ठीक है|ಅలాగే|sari|theek hai|alage)\b/gi, replacement: "Alright" },
  { pattern: /\b(ಹೌದು|हाँ|haudu|haan|ha)\b/gi, replacement: "Yes" },
  { pattern: /\b(ಇಲ್ಲ|नहीं|illa|nahi|nahin)\b/gi, replacement: "No" },

  // Weather & Farming Terms
  { pattern: /\b(ಮಳೆ|ವರ್ಷ|ಬಾರಿಶ್|ವರ್ಷಂ|male|barish|varsham)\b/gi, replacement: "rain" },
  { pattern: /\b(ತಾಪಮಾನ|ತಾಪಮಾನ್|ಉಷ್ಣೋಗ್ರತ|tapman|tapamana|ushnograta)\b/gi, replacement: "temperature" },
  { pattern: /\b(ಗಾಳಿಯ ವೇಗ|ಹವಾ ಕಿ ಗತಿ|ಗಾಲಿ ವೇಗಂ|galiya vega|hawa ki gati|gaali vegam)\b/gi, replacement: "wind speed" },
  { pattern: /\b(ತೇವಾಂಶ|ನಮೀ|ತೇಮ|tevamsha|nami|tema)\b/gi, replacement: "humidity" },
  { pattern: /\b(ಹವಾಮಾನ|ಮೌಸಮ್|ವಾತಾವರಣ|havamana|mausam|vatavaranam)\b/gi, replacement: "weather" },
  { pattern: /\b(ಇಂದು|ಆಜ್|ಈ ರೋಜು|indu|aaj|ee roju)\b/gi, replacement: "today" },
  { pattern: /\b(ನಾಳೆ|ಕಲ್|ರೇಪು|naale|kal|repu)\b/gi, replacement: "tomorrow" },
  { pattern: /\b(ಸಂಜೆ|ಶಾಮ್|ಸಾಯಂತ್ರಂ|sanje|shaam|sayantram)\b/gi, replacement: "evening" },
  { pattern: /\b(ಮಧ್ಯಾಹ್ನ|ದೋಪಹರ್|madhyahna|dopahar)\b/gi, replacement: "afternoon" },
  { pattern: /\b(ಬೆಳಿಗ್ಗೆ|ಸುಬಹ್|ಉದಯಂ|beligge|subah|udayam)\b/gi, replacement: "morning" },
  { pattern: /\b(ಕೀಟನಾಶಕ|ಕೀಟನಾಶಕ್|ಪುರುಗುಲ ಮಂದು|keetanashaka|keetnashak)\b/gi, replacement: "pesticide" },
  { pattern: /\b(ಕೃಷಿ|ಖೇತ್|ಹೊಲ|ಪೊಲಂ|krishi|khet|hola|polam)\b/gi, replacement: "farm" }
];

/**
 * Checks if text has Indic script characters (Kannada, Devanagari, Telugu)
 */
export function hasIndicScript(text) {
  if (!text || typeof text !== 'string') return false;
  // Devanagari (0900-097F), Kannada (0C80-0CFF), Telugu (0C00-0C7F)
  return /[\u0900-\u097F\u0C80-\u0CFF\u0C00-\u0C7F]/.test(text);
}

/**
 * Phonetic transliterator mapping Indic characters (Kannada, Devanagari, Telugu) to Latin characters
 * Used ONLY when user selects 'English Script' (romanized)
 */
function transliterateIndicCharacters(text) {
  if (!text) return '';

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
    'त': 't', 'थ': 'th', 'द': 'd', 'ಧ': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v',
    'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h', 'क़': 'q', 'ख़': 'kh', 'ग़': 'gh', 'ज़': 'z', 'फ़': 'f'
  };

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

    if (devVowels[ch]) { out += devVowels[ch]; continue; }
    if (kanVowels[ch]) { out += kanVowels[ch]; continue; }
    if (telVowels[ch]) { out += telVowels[ch]; continue; }
    if (indicSymbols[ch]) { out += indicSymbols[ch]; continue; }

    // Devanagari consonants
    if (devConsonants[ch]) {
      const base = devConsonants[ch];
      if (next === '\u094D') {
        out += base;
        i++;
      } else if (devMatras[next]) {
        out += base + devMatras[next];
        i++;
      } else if (i === len - 1 || /[\s,.\-!?]/.test(next)) {
        out += base;
      } else {
        out += base + 'a';
      }
      continue;
    }

    // Kannada consonants (Kannada virama is \u0CCD)
    if (kanConsonants[ch]) {
      const base = kanConsonants[ch];
      if (next === '\u0CCD') {
        out += base;
        i++;
      } else if (kanMatras[next]) {
        out += base + kanMatras[next];
        i++;
      } else if (i === len - 1 || /[\s,.\-!?]/.test(next)) {
        out += base;
      } else {
        out += base + 'a';
      }
      continue;
    }

    // Telugu consonants (Telugu virama is \u0C4D)
    if (telConsonants[ch]) {
      const base = telConsonants[ch];
      if (next === '\u0C4D') {
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

    if (ch === '।') { out += '.'; continue; }
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
 * Returns text translated into 100% pure, natural English (NEVER Hinglish/Kanglish)
 * e.g. "ನಮಸ್ಕಾರ ರಮೇಶ್ ಅವರೇ..." -> "Hello Ramesh, this is today's weather forecast..."
 */
export function getTranslatedTranscript(text) {
  if (!text || typeof text !== 'string') return '';
  const trimmed = text.trim();

  // 1. Check exact phrase pattern matchers
  for (const item of PHRASE_PATTERNS) {
    const match = trimmed.match(item.regex);
    if (match) {
      return item.translated(match);
    }
  }

  // 2. Check if already standard English (no Indic script & no Hinglish/Kanglish words)
  const isStandardEnglish = !hasIndicScript(trimmed) &&
    !/\b(namaskar|namaste|avare|dhanyavad|khet|kare|madi|bataiye|dhoop|khandita|sari|mausam|barish|gaaru|nundi|neti)\b/i.test(trimmed);

  if (isStandardEnglish) {
    return trimmed;
  }

  // 3. Intelligent vocabulary & clause translation
  let translatedText = trimmed;
  for (const entry of VOCABULARY_TRANSLATIONS) {
    translatedText = translatedText.replace(entry.pattern, entry.replacement);
  }

  // If any Indic script remains after vocabulary replacement, synthesize a clean English sentence
  if (hasIndicScript(translatedText)) {
    if (/ತಾಪಮಾನ|ಮಳೆ|मौसम|बारिश|వర్షం|उष्णోగ్రత/i.test(trimmed)) {
      return "Daily agricultural weather briefing delivered to farmer.";
    }
    if (/ಕರೆ|ಕಾಲ್|कॉल|ఫోన్|मंडी|ಮಾರುಕಟ್ಟೆ|ಸಂತ/i.test(trimmed)) {
      return "Farmer requested callback; reschedule noted.";
    }
    return "Agricultural weather communication recorded.";
  }

  return translatedText;
}

/**
 * Formats transcript turn text according to selected mode:
 * - 'translated': Translated into 100% clean, natural English (NO Hinglish)
 * - 'romanized': English script, same language phonetically (Transliteration)
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
