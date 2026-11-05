/**
 * Conversational Logic, Intent Classifier & Guardrail Engine
 * 
 * Handles:
 * 1. Weather Doubts (resolves queries strictly using the 4 meteorological parameters)
 * 2. Specific Time Reschedule / Callback Flag (extracts requested time, sets Callback Requested, populates scheduled_callback_time)
 * 3. Non-Weather Escalation (strictly declines agronomic/chemical advice, flags Non-Weather Inquiry & status Escalated)
 * 4. Multi-lingual support: Hindi, English, Kannada (Native scripts & Romanized)
 */

// Comprehensive keyword patterns covering Latin transliterations and native scripts
const AGRONOMIC_PATTERNS = [
  /pesticide/i,
  /insecticide/i,
  /fungicide/i,
  /fertilizer/i,
  /chemical/i,
  /urea/i,
  /dap/i,
  /spray/i,
  /dawai/i,
  /keeda/i,
  /keede/i,
  /rog/i,
  /bimaari/i,
  /bimar/i,
  /khad/i,
  /crop disease/i,
  /stem borer/i,
  /pest/i,
  /कीटनाशक/i,
  /दवाई/i,
  /कीड़ा/i,
  /कीड़े/i,
  /बीमारी/i,
  /रोग/i,
  /खाद/i,
  /यूरिया/i,
  /ಔಷಧಿ/i,
  /ಕೀಟನಾಶಕ/i,
  /ಗೊಬ್ಬರ/i,
  /ಹುಳು/i,
  /ರೋಗ/i
];

const RESCHEDULE_PATTERNS = [
  /call (?:me )?(?:back )?(?:at|after) ([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)/i,
  /call (?:back )?at ([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)/i,
  /shaam ko ([0-9]{1,2}|ek|do|teen|chaar|paanch|chhe)\s*baje/i,
  /subah ([0-9]{1,2}|ek|do|teen|chaar|paanch|chhe)\s*baje/i,
  /dopehar ([0-9]{1,2}|ek|do|teen|chaar|paanch|chhe)\s*baje/i,
  /([0-9]{1,2}(?::[0-9]{2})?\s*(?:baje|pm|am))/i,
  /call later/i,
  /busy right now/i,
  /abhi (?:khet|vyast|kaam) me hu/i,
  /शाम को ([0-9]{1,2})\s*बजे/i,
  /दोपहर ([0-9]{1,2})\s*बजे/i,
  /सुबह ([0-9]{1,2})\s*बजे/i,
  /ಸಂಜೆ ([0-9]{1,2})\s*ಗಂಟೆಗೆ/i,
  /ನಾಳೆ ಕರೆ ಮಾಡಿ/i,
  /व्यस्त हूँ/i,
  /व्यस्त/i,
  /ಮಾರುಕಟ್ಟೆ/i
];

const WEATHER_DOUBT_PATTERNS = [
  /rain|barish|weather|mausam|temp|garmi|hawa|wind|humidity|nami|dhup/i,
  /बारिश|मौसम|वर्षा|तापमान|हवा|गर्मी|नमी|धूप/i,
  /ಮಳೆ|ಹವಾಮಾನ|ತಾಪಮಾನ|ಗಾಳಿ|ತೇವಾಂಶ/i
];

const HINDI_NUM_WORDS = {
  'ek': '1:00 PM',
  'do': '2:00 PM',
  'teen': '3:00 PM',
  'chaar': '4:00 PM',
  'paanch': '5:00 PM',
  'chhe': '6:00 PM'
};

/**
 * Classifies an incoming farmer statement and returns conversation result,
 * status transition, disposition, and updated fields.
 */
export function processFarmerUtterance(farmerUtterance, weather, options = {}) {
  const rawLang = String(options.language || '').toLowerCase();
  const isEnglish = rawLang.includes('eng');
  const isKannada = rawLang.includes('kan');
  const text = (farmerUtterance || '').trim();

  // 1. NON-WEATHER / AGRONOMIC INQUIRY GUARDRAIL CHECK
  const isAgronomic = AGRONOMIC_PATTERNS.some(regex => regex.test(text));
  if (isAgronomic) {
    let speechResponse = '';
    if (isEnglish) {
      speechResponse = "As Agrythm Connect Weather Voice Assistant, I can only provide meteorological advisories and cannot give chemical or agronomic recommendations. Your inquiry has been escalated to an agronomist who will contact you shortly.";
    } else if (isKannada) {
      speechResponse = "ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್ ಕೇವಲ ಹವಾಮಾನ ಮುನ್ಸೂಚನೆಯನ್ನು ಮಾತ್ರ ಒದಗಿಸುತ್ತದೆ, ಕೃಷಿ ರಾಸಾಯನಿಕ ಸಲಹೆಯನ್ನಲ್ಲ. ನಿಮ್ಮ ವಿಚಾರಣೆಯನ್ನು ನಮ್ಮ ಕೃಷಿ ತಜ್ಞರಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ, ಅವರು ಶೀಘ್ರದಲ್ಲೇ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುತ್ತಾರೆ.";
    } else {
      speechResponse = "एग्रिद्म कनेक्ट मौसम सहायक केवल मौसम की जानकारी दे सकता है, कीटनाशक या कृषि सलाह नहीं। आपका सवाल हमारे कृषि विशेषज्ञ को भेज दिया गया है, वे जल्द ही आपसे संपर्क करेंगे।";
    }

    return {
      intent: 'NON_WEATHER_ESCALATION',
      status: 'Escalated',
      disposition: 'Non-Weather Inquiry',
      scheduled_callback_time: null,
      speech_response: speechResponse,
      escalation_reason: 'Agronomic/Chemical boundary guardrail triggered: ' + text
    };
  }

  // 2. SPECIFIC TIME RESCHEDULE / CALLBACK FLAG
  for (const regex of RESCHEDULE_PATTERNS) {
    const match = text.match(regex);
    if (match) {
      let extractedTime = extractTimeSlot(text, match);
      let speechResponse = '';
      if (isEnglish) {
        speechResponse = `Understood. We have noted your request and scheduled a callback for ${extractedTime}. Thank you and have a safe day in the field.`;
      } else if (isKannada) {
        speechResponse = `ಖಂಡಿತ. ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು ದಾಖಲಿಸಿಕೊಳ್ಳಲಾಗಿದೆ ಮತ್ತು ${extractedTime} ಕ್ಕೆ ಕಾಲ್‌ಬ್ಯಾಕ್ ನಿಗದಿಪಡಿಸಲಾಗಿದೆ. ಧನ್ಯವಾದಗಳು.`;
      } else {
        speechResponse = `समझ गया। हमने आपका समय नोट कर लिया है और ${extractedTime} पर दोबारा कॉलबैक शेड्यूल किया है। धन्यवाद।`;
      }

      return {
        intent: 'CALLBACK_REQUESTED',
        status: 'Completed',
        disposition: 'Callback Requested',
        scheduled_callback_time: extractedTime,
        speech_response: speechResponse,
        callback_note: `Farmer requested callback at ${extractedTime}`
      };
    }
  }

  // 3. WEATHER DOUBTS RESOLUTION (strictly grounded in the 4 parameters)
  const isWeatherDoubt = WEATHER_DOUBT_PATTERNS.some(regex => regex.test(text));

  let speechResponse = '';
  if (isEnglish) {
    speechResponse = `Today's weather for your area: Temperature is ${weather.temperature}°C, Wind speed is ${weather.wind_speed} km/h, Precipitation chance is ${weather.rainfall_probability}%, and Humidity is ${weather.relative_humidity}%. ${weather.rainfall_probability >= 50 ? 'Rain is expected, please plan operations accordingly.' : 'Clear conditions favorable for work.'}`;
  } else if (isKannada) {
    speechResponse = `ಇಂದು ನಿಮ್ಮ ಪ್ರದೇಶದ ಹವಾಮಾನ: ತಾಪಮಾನ ${weather.temperature}°C, ಗಾಳಿಯ ವೇಗ ಗಂಟೆಗೆ ${weather.wind_speed} ಕಿಮೀ, ಮಳೆಯ ಸಾಧ್ಯತೆ ${weather.rainfall_probability}% ಮತ್ತು ತೇವಾಂಶ ${weather.relative_humidity}% ಇದೆ.`;
  } else {
    speechResponse = `आज आपके इलाके का मौसम: तापमान ${weather.temperature}°C, हवा की गति ${weather.wind_speed} किमी/घंटा, बारिश की संभावना ${weather.rainfall_probability}% और नमी ${weather.relative_humidity}% है। ${weather.rainfall_probability >= 50 ? 'बारिश के आसार हैं, ध्यान रखें।' : 'मौसम सामान्य रहेगा।'}`;
  }

  return {
    intent: isWeatherDoubt ? 'WEATHER_DOUBT_RESOLVED' : 'WEATHER_DELIVERED',
    status: 'Completed',
    disposition: 'Weather Delivered',
    scheduled_callback_time: null,
    speech_response: speechResponse
  };
}

/**
 * Extracts a normalized time string from utterance
 */
function extractTimeSlot(text, match) {
  const lower = text.toLowerCase();
  
  if (lower.includes('shaam ko 5') || lower.includes('5 baje') || lower.includes('5 pm') || lower.includes('ಸಂಜೆ 5') || text.includes('5 बजे') || text.includes('शाम को 5')) {
    return 'Today, 5:00 PM';
  }
  if (lower.includes('shaam ko') || lower.includes('shaam') || text.includes('शाम')) {
    for (const [w, t] of Object.entries(HINDI_NUM_WORDS)) {
      if (lower.includes(w)) return `Today, ${t}`;
    }
    return 'Today, 5:00 PM';
  }
  if (lower.includes('2 baje') || lower.includes('after 2 pm') || lower.includes('2 pm') || text.includes('2 बजे')) {
    return 'Today, 2:00 PM';
  }
  if (lower.includes('3 baje') || lower.includes('3 pm') || text.includes('3 बजे')) {
    return 'Today, 3:00 PM';
  }
  if (lower.includes('4:30 pm') || lower.includes('4:30')) {
    return 'Today, 4:30 PM';
  }
  if (lower.includes('kal') || lower.includes('tomorrow') || lower.includes('ನಾಳೆ') || text.includes('कल')) {
    return 'Tomorrow, 10:00 AM';
  }

  const rawMatch = match[1] || match[0];
  if (rawMatch) {
    const cleaned = rawMatch.replace(/baje|बजे|ಗಂಟೆಗೆ/i, '').trim();
    if (/^[0-9]{1,2}$/.test(cleaned)) {
      const h = Number(cleaned);
      const isEvening = h <= 7;
      return `Today, ${h}:00 ${isEvening ? 'PM' : 'AM'}`;
    }
    return `Today, ${rawMatch}`;
  }

  return 'Today, 5:00 PM';
}

/**
 * Generates initial greeting and 4-parameter weather delivery script
 */
export function generateInitialGreeting(farmer, weather) {
  const lang = String(farmer.preferred_language || '').toLowerCase();

  if (lang.includes('eng')) {
    return {
      language: 'English',
      message: `Hello ${farmer.farmer_name || 'Farmer'}, this is your Agrythm Connect daily weather advisory for ${farmer.village || farmer.district}. Today's temperature is ${weather.temperature}°C with relative humidity at ${weather.relative_humidity}%. Wind speed is ${weather.wind_speed} km/h, and precipitation probability is ${weather.rainfall_probability}%. Do you have any questions about today's weather?`
    };
  }

  if (lang.includes('kan')) {
    return {
      language: 'Kannada',
      message: `ನಮಸ್ಕಾರ ${farmer.farmer_name || 'ರೈತ ಮಿತ್ರರೆ'}, ಇದು ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್‌ನಿಂದ ${farmer.village || farmer.district} ಗೆ ಇಂದಿನ ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ. ಇಂದಿನ ತಾಪಮಾನ ${weather.temperature}°C, ಗಾಳಿಯ ವೇಗ ${weather.wind_speed} ಕಿಮೀ/ಗಂಟೆ, ಮಳೆಯ ಸಾಧ್ಯತೆ ${weather.rainfall_probability}% ಮತ್ತು ತೇವಾಂಶ ${weather.relative_humidity}% ಆಗಿದೆ. ಹವಾಮಾನದ ಕುರಿತು ಯಾವುದೇ ಪ್ರಶ್ನೆಗಳಿವೆಯೇ?`
    };
  }

  return {
    language: 'Hindi',
    message: `नमस्ते ${farmer.farmer_name || 'किसान भाई'}, यह एग्रिद्म कनेक्ट से ${farmer.village || farmer.district} के लिए आपका दैनिक मौसम समाचार है। आज का तापमान ${weather.temperature}°C और नमी ${weather.relative_humidity}% रहेगी। हवा की गति ${weather.wind_speed} किमी/घंटा और बारिश की संभावना ${weather.rainfall_probability}% है। क्या आप आज के मौसम के बारे में कुछ पूछना चाहते हैं?`
  };
}
