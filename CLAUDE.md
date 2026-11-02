# CLAUDE.md — repository map

Three areas, each with its own rules. Read the `CLAUDE.md` inside the folder you are working in.

- `Pilot/` the earlier text-only prototype. Do not change it for Gate Zero work. Its tests must keep passing (`cd Pilot && python -m pytest -q`).
- `gate0/` Gate Zero weather-call prototype. Active work. Rules in `gate0/CLAUDE.md`.
- `final-product/` upcoming integrated product. Placeholder only; no code until the team starts it.

Shared rules: no farmer personal data or provider keys in git; the voice never claims to be human (the opening does not announce it is an AI, decided 2 Nov 2026); only consented farmers are called; small commits, tests first; record decisions in `docs/` of the area.
