# Agent prompt edits: interruptions and long answers (proposed 16 Nov 2026)

Edits 1 to 4 below were applied to agent version 15 on 16 Nov (the draft was committed as 15). Apply any new change to the **draft** only, test with a real call,
then commit a new version and pin it (`SARVAM_APP_VERSION` in Render, and the inbound deployment, which must be paused to edit).

## What was seen on a real call
1. The farmer spoke while the agent was talking and the agent carried on instead of stopping and answering.
2. When the farmer said "understood" early (before the agent had finished), the agent kept talking.

## Why a prompt change helps, and what it cannot do
Stopping the audio the moment the farmer speaks is done by Sarvam's voice detection, not by the prompt (settings below). What the
prompt controls is how long each turn is, what the agent does with an interruption once it hears it, and what it does when the
farmer says "understood" in the middle of the weather. Long turns make a missed interruption feel much worse, so the prompt asks
for short turns. These edits are general rules for how the agent speaks, not a patch for one sentence.

## Prompt edits (exact `old_text` to `new_text`, state `start`)

### 1. New section "HOW YOU SPEAK" before "WHAT YOU KNOW FOR THIS CALL"
old_text:
```
\n\nWHAT YOU KNOW FOR THIS CALL\n
```
new_text:
```
\n\nHOW YOU SPEAK\n- Keep every turn short: one or two short sentences (about 20 words), in simple spoken words. Never read out a long paragraph.\n- Give information in small pieces and let the farmer answer between them.\n- If the farmer starts speaking while you are speaking, stop at once, listen to everything they say, and answer what they just said. Do not finish your old sentence and do not go back to it unless they ask.\n- Never repeat anything you have already said unless they ask you to.\n\nWHAT YOU KNOW FOR THIS CALL\n
```

### 2. Weather given in two short parts, and what to do if the farmer says "understood" in the middle
old_text:
```
and then give the weather update right away, in short natural sentences: the place, today's lowest and highest temperature, wind speed, chance of rain and humidity, using exactly the figures above. Do not ask whether it is a good time to talk. Then ask once whether they understood it.
```
new_text:
```
and then give the weather update right away, in two short parts: first the place and today's lowest and highest temperature; then the wind speed, chance of rain and humidity, using exactly the figures above. Do not ask whether it is a good time to talk. If the farmer says they understood, or says okay, while you are still giving it, stop at once: do not start again and do not repeat what you already said; say any of the facts you have not yet said in one short sentence, and then ask once whether they have any question. When all of it has been given, ask once whether they understood it.
```

### 3. "Understood / okay" at any point
old_text:
```
   - Understood / okay: ask once, in simple words, whether they have any other question about this weather. Do not end the call until they say they are clear and have nothing more to ask.
```
new_text:
```
   - Understood / okay (at any point): do not repeat or add to what you said. If some facts were not given yet, give them in one short sentence. Then ask once, in one short sentence, whether they have any other question about this weather. Do not end the call until they say they are clear and have nothing more to ask.
```

### 4. Interruptions
old_text:
```
   - If the farmer interrupts, answer the new question instead of repeating your earlier answer.
```
new_text:
```
   - If the farmer interrupts you, stop speaking immediately, then answer only the new question in one or two short sentences instead of repeating your earlier answer.
```

Nothing else in the prompt changes: the farmer-calling-back branch, the callback rules, the strict limits, the closing and every Hindi,
Kannada and Telugu phrase stay as they are. Native-speaker review of the language lines is still pending.

## Voice detection (draft change to try, `interaction_config.vad_config.speech_frame_config`)
Version 14 already has `volume_threshold -45`, `silence_duration_frames 6`, `analysis_frame_size 8`, and the interruption still did not stop the
voice. The allowed values are `volume_threshold` in -50, -45, -40, -35, -25, -20 (more negative should be more sensitive) and
`silence_duration_frames` in 4, 6, 9, 12 (`analysis_frame_size` is that number plus 2).
- Try `volume_threshold -50` and leave the rest. A phone line is quiet, so a more sensitive threshold lets a soft voice count as speech.
- `num_initial_ignored_frames` cannot be changed through the connector; if the voice only fails to stop in the first seconds of a
  sentence, ask Sarvam what its default is and whether it can be shortened.
- Too sensitive a threshold can let line noise or an echo of the agent's own voice cut it off: test once on speaker and once with earphones.
- If the voice still does not stop, that is Sarvam's platform behaviour and should go to Sarvam support with a call id and the time.

## How to test
Three calls, each on a real phone: (1) interrupt the agent in the middle of the weather with a question; (2) say "understood" while
it is still giving the weather; (3) say nothing until the end. Check that the agent stops and answers, that it does not start the
weather again, and that `understood_weather` is still recorded as `yes` on the dashboard.


## Found in the first real tests (17 Nov), to apply when the Sarvam connector is back
1. **Farmer details missing on an incoming call, and weather invented.** The cohort push to the inbound line was failing (HTTP 422), so the agent had a blank name and
   no weather and still spoke weather figures. Fix the push first (the "call-back line" note now carries Sarvam's reason). In the prompt, add to WHAT YOU KNOW:
   "Never say a temperature, wind speed, chance of rain, humidity, place or name that is not written in the values above. If a value is empty, say nothing about it."
2. **Silence after the greeting, then the call ends.** The agent has an inactivity nudge at 5 s ("Hey, are you still on the call?") and ends the call after consecutive
   nudges. A farmer needs longer to answer a long greeting on a phone line. Change the nudges to a first nudge at about 12 s and a second at about 20 s, and end only after
   three, not one or two. In the prompt, replace the rule "Only says hello, stays silent...: repeat your greeting once. If there is still no real reply, say the normal goodbye
   and end" with: wait; after the first silence ask once "Can you hear me?" in the call's language; end only after a third silence, with the normal goodbye.
3. **Voice threshold.** Version 15 has `volume_threshold -50` (more sensitive). If line noise or the agent's own echo is being taken for speech, the farmer's real words can be missed and
   the agent thinks they are silent. Put it back to -45 and test the silence again before touching anything else.
4. **An unknown or inactive caller.** The agent ends the call after one sentence (already in version 15); the line still answers it. Stopping the answer itself is for Sarvam.


## Edits ready for v17 (19 Nov), APPLIED 19 Nov: committed as v17, inbound deployment moved to v17 (draft only, then commit, pause, move, resume)
These replace the 17 Nov silence item 2. The existing script is adjusted, nothing new is written.

1. **Silence (decided 19 Nov).** If the farmer is silent for 7 seconds the agent asks "are you there?"; after 10 more seconds of silence it asks again;
   if there is still no reply it ends the call politely. In Sarvam's silence nudges (`configure_silence_nudges`): first nudge at 7 s, second at 10 s after
   the first, end the interaction after the second nudge goes unanswered. In the prompt, replace the bullet that starts
   "Only says hello, stays silent, or you cannot hear them" with:
   "Only says hello, stays silent, or you cannot hear them: do not give the weather. When the farmer has been silent for about 7 seconds, ask once, in the
   call's language, whether they are there (Hindi \"क्या आप वहाँ हैं?\", Kannada \"ನೀವು ಅಲ್ಲಿದ್ದೀರಾ?\", Telugu \"మీరు అక్కడ ఉన్నారా?\", English \"Are you there?\"),
   then wait about 10 seconds. If they are still silent, ask once more. If there is still no reply, say politely that they may be busy and that we will call
   them again later (Hindi \"लगता है आप व्यस्त हैं। हम आपको बाद में फ़ोन करेंगे।\", Kannada \"ನೀವು ಬ್ಯುಸಿ ಇರಬಹುದು. ನಾವು ನಂತರ ಕರೆ ಮಾಡುತ್ತೇವೆ.\",
   Telugu \"మీరు బిజీగా ఉండవచ్చు. మేము తర్వాత కాల్ చేస్తాము.\", English \"You may be busy. We will call you later.\"), say the normal goodbye from CLOSING and
   end the call. Never end the call before the second 'are you there' has had its 10 seconds."
   The call then counts as not reached, so the retry rules call the farmer again later.
2. **Already served today.** In the bullet "if we already gave them today's weather and they understood it", say in one short sentence that today's weather was
   already shared and the next update comes tomorrow, say the normal goodbye and end; do not give the weather again, even if asked. The backend `completed`
   context says the same (PR 63). This dry-ran clean on the draft (prompt sha 8d50c31a735deb9d).
