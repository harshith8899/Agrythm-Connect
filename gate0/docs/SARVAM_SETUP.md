# Sarvam calling setup and the first tests

Gate Zero calls through a Sarvam Voice Agent. Our code builds the weather message, including the AI disclosure. Sarvam dials the farmer, and the agent speaks that message as its first line. The result (answered, no answer, busy or failed) is read back from Sarvam's Analytics API.

## 1. Dashboard setup (one time)
1. **Phone number.** Under Deploy → Phone numbers, rent a number from Sarvam or connect Exotel, Plivo or another provider. Note the **connection ID** and the agent's **phone number** in E.164 form (+91...).
2. **Agent.** Create an agent named `Agrythm connect - Weather info`. The agent opens the call itself, asks if it is a good time to talk, then gives the weather from per-farmer variables that our backend sends. Settings:
   - **Languages:** Hindi, Kannada, Telugu and English. Do not write a prompt rule that tells the agent to switch language: Sarvam switches by itself and rejects such a rule.
   - **Greeting (intro):** short, with variables, for example: "Hello {{farmer_name}}. I am Chetan Dabke's assistant, calling on behalf of Agrythm to share a short weather update for {{place_name}}. Is this a good time to talk?" Sarvam translates it for Hindi and Kannada.
   - **Input variables** (all type string, set per call by the backend, names must match `script.weather_variables`): `farmer_name`, `place_name`, `temp_min_c`, `temp_max_c`, `wind_kmh`, `rain_chance_pct`, `humidity_pct`, and `now_text` (today's date and time in India, from `script.format_now`, so the agent can confirm a callback's day and morning or evening). Sarvam answers HTTP 422 if the backend sends a name the agent does not declare.
   - **Output variables** (filled by Sarvam after each connected call):
     - `call_summary` (string): one or two plain English sentences on whether the farmer heard the update and what they asked. No phone numbers, names of others or advice.
     - `callback_time` (string): when the farmer asked to be called back, in one of three forms: `HH:MM` on the 24-hour clock (later today), `tomorrow HH:MM`, or `in N minutes` / `in N hours`; empty if no usable time was settled.
     - `understood_weather` (enum `yes`, `no`, `unclear`).
     - `stop_calls_requested` (enum `yes`, `no`).
   - **Instruction:** kept in the agent (the committed version is the source of truth). In short: Chetan Dabke's AI assistant for Agrythm; never claims to be human, and says it is an AI only if asked; after "yes, good time" it gives place, lowest and highest temperature, wind, chance of rain and humidity using exactly the variable values; if a value is empty it says the weather is not available and ends; answers weather questions only from those facts, never invents numbers; for anything else says it can only share the weather and ends; no farming, financial or medical advice; no phone numbers or personal details; a callback request (busy, or "call me later") gets a very short flow: if the day and morning or evening are not clear it asks one question to settle them (naming the real date from `now_text`), then confirms the time in one sentence with thanks and ends; no weather and no comments on being busy; calls only between 8 in the morning and 7 in the evening; ends only after the farmer says they are clear, always with the goodbye ("Thank you! Have a good day from Agrythm." in the call's language).
   - **Tools:** keep **End call** on.
   - **Call settings:** maximum call length 1500 s (the largest Sarvam allows); the agent ends the call itself once the farmer is clear.
   - Commit the version and note the **version number**. Calls use only committed versions, so every change needs a new commit and a new `SARVAM_APP_VERSION`. Do not edit an older version in the dashboard while someone else edits (a save from a stale page overwrites newer changes).
3. **IDs and key.**
   - Org ID and workspace ID: from the dashboard URL or Settings.
   - Agent ID: agent's ··· menu → Copy agent ID.
   - API key: Settings → API Key. This key goes in `X-API-Key` and may differ from the speech-API key.

## 2. `.env` (never commit)
```
GATE0_VOICE=sarvam_agent
GATE0_TELEPHONY=sarvam_agent
GATE0_MAX_ATTEMPTS=1            # while testing on free credits: one dial per farmer per day
GATE0_CALL_MODE=campaign        # Sarvam schedules and dials; see section 3
SARVAM_AGENT_API_KEY=...
SARVAM_ORG_ID=...
SARVAM_WORKSPACE_ID=...
SARVAM_APP_ID=...
SARVAM_APP_VERSION=8               # the committed agent version in use
SARVAM_CONNECTION_ID=...
SARVAM_AGENT_PHONE=+91...
```

## 3. Scheduling inside Sarvam (campaign mode)
Sarvam Campaigns do the timing, dialling and retries. A campaign dials each contact once (plus retries), but our message changes every day. So each morning our code adds that day's farmers, with that day's weather message, to the campaign.

```
python -m weathercall.campaign create --start 2026-10-27 --days 4 --time 09:00 --window-end 11:00
python -m weathercall.schedule activate --start 2026-10-27 --days 4 --mode campaign
```
- `create` makes the campaign in Sarvam: 09:00 to 11:00 IST every day for 4 days, with retries from `GATE0_MAX_ATTEMPTS` and `GATE0_RETRY_GAP_MINUTES`. It shows in the dashboard under Deploy → Campaigns.
- The scheduled task runs `campaign daily` at 08:30. It pulls yesterday's results into our ledger, checks today's farmers (consent, weather saved) and pushes only the eligible ones. Each farmer goes in with their own variables (`app_variables`) and their language; the agent's intro opens the call and the agent speaks the weather from those variables. A farmer is never pushed twice for the same day.
- The task runs one extra morning, so the last day's results are pulled in too.
- Manual control: `campaign push`, `campaign sync --date D`, `campaign status`.
- `campaign sync` also saves every attempt's details in the `call_details` table for the monitoring UI: Sarvam's `interaction_id`, who ended the call (`ended_by`), the full failure reason, the `call_summary` output variable and, for connected calls, the transcript as JSON (`role`, `content`, `language_name` per turn). Anything that looks like a phone number (10 or more digits) is replaced with `[number removed]` before it is stored. Sarvam's `user_contact` field is never read.
- Keep the window long enough for every retry (3 tries x 30 min fits in 09:00 to 11:00). Otherwise a retry could spill into the next morning.

## 4. Test plan on the 85 free credits (cheapest first)
| # | Test | Credits | Pass when |
|---|---|---|---|
| 1 | `python -m pytest -q` | 0 | all green (fake Sarvam server) |
| 2 | Agent playground test call in the dashboard, English | small | agent reads a pasted weather line and ends the call |
| 3 | One real call to **your own** phone, English: one-row sheet in `data/test.csv`, `GATE0_FARMERS_FILE=data/test.csv`, then `python -m weathercall.cli` | 1 call | phone rings, voice says it is an AI, gives weather, hangs up; CLI shows `answered` |
| 4 | Same, with Hindi in the sheet | 1 call | Hindi message spoken; note wording for native review |
| 5 | Same, but reject the call | 1 call | CLI shows `unanswered` or `failed` with a reason |
| 6 | Run the CLI again the same day | 0 | farmer shown as already handled; phone does not ring |

After test 3, check the dashboard's credit balance to see what one 40-second call costs. Then decide how many teammates (with their consent) can be in the 4-day trial sheet.

Only call numbers of people who have agreed to be called, and only team members during testing.
