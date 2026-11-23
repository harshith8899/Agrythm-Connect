# Incoming calls: moved to Gate 1 (decided 23 Nov 2026)

The client does not need incoming calls in Gate Zero. Gate Zero calls farmers; it does not answer them. What was built and learned is kept here for Gate 1.

## What exists in the Gate Zero code (kept, switched off by leaving the setting empty)
- `SARVAM_INBOUND_DEPLOYMENT_ID` empty in Render: no farmer details are pushed to the call-back line, no "call-back line could not be updated" notes appear, and incoming calls are not looked at.
- With it set: the backend pushes each registered farmer (name, place, weather, what happened today) to the line, logs every incoming call (Incoming line panel, 'In' mark in the call log), turns a farmer's call into their result, and sends the weather email after a successful one.

## What was found
- Sarvam's JSON 'stream' route for deployments answered every push with HTTP 422 'User Identifier is not supported for deployments', also for a request without that field (23 Nov, the failure note listed the fields sent). Their docs list the field as allowed. The CSV upload route for the same deployment accepts the data, and the backend now uses it. Still unverified: whether a new cohort for a number replaces the old record, and how an incoming call is matched in practice.
- Without farmer details on the line, every caller looks unknown and is refused; Sarvam cannot refuse a number before the line answers.
- Incoming calls reach the dashboard only after Sarvam reports them (minutes), matched by the caller's number hash.

## Design for Gate 1 (the team's idea, 23 Nov)
1. The line should not answer at once. It rings while our backend looks the caller up and fetches their data.
2. When the data is ready, the agent answers and already knows the farmer, the weather and what happened today.
3. If the data is not ready after a few seconds, the agent tells the caller politely that it cannot help now and to try again, and the call ends.
4. Option that avoids Sarvam cohorts: the agent calls an API tool on our server at the start of the call with the caller's number, and our server answers with the details. Needs a protected endpoint, a token for the tool and a new agent version.
5. Rules that carry over: only registered, consented, active farmers are served; one served call per farmer per day; unknown numbers are refused politely; never read out weather with an empty value.
