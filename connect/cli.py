"""Text CLI for TRL 3: talk to the agent in English, Hindi or Hinglish."""
from __future__ import annotations

import argparse
import json
import time

from .db import connect, get_conversation
from .events import create_event
from .orchestrator import ConversationSession
from .seed import seed_demo


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Agrythm Connect text prototype (TRL 3)")
    p.add_argument("--db", default=":memory:", help="SQLite path (default: in-memory demo)")
    p.add_argument("--farmer", type=int, help="farmer id to call")
    p.add_argument("--lang", choices=("hi", "en"),
                   help="override the farmer's stored language for this call")
    p.add_argument("--list", action="store_true", help="list demo farmers and exit")
    args = p.parse_args(argv)

    conn = connect(args.db)
    if conn.execute("SELECT COUNT(*) FROM farmers").fetchone()[0] == 0:
        seed_demo(conn)

    if args.list or not args.farmer:
        for r in conn.execute(
            "SELECT f.id, f.name, f.language, cc.crop, a.id AS adv, a.approved "
            "FROM farmers f JOIN farms fa ON fa.farmer_id=f.id JOIN crop_cycles cc ON cc.farm_id=fa.id "
            "JOIN advisories a ON a.crop_cycle_id=cc.id ORDER BY f.id"
        ):
            status = "approved" if r["approved"] else "NOT approved"
            print(f"{r['id']}: {r['name']} [{r['language']}] {r['crop']} advisory {r['adv']} ({status})")
        return 0

    row = conn.execute(
        "SELECT a.id AS adv, a.crop_cycle_id AS cyc FROM advisories a "
        "JOIN crop_cycles cc ON cc.id=a.crop_cycle_id JOIN farms f ON f.id=cc.farm_id "
        "WHERE f.farmer_id=? AND a.approved=1 ORDER BY a.id DESC LIMIT 1", (args.farmer,)).fetchone()
    if row is None:
        print("No approved advisory for this farmer; nothing to call about.")
        return 1

    ev = create_event(conn, "advisory_approved", args.farmer, row["cyc"], row["adv"],
                      dedupe_key=f"cli:{time.time()}")
    session = ConversationSession(conn, ev.conversation_id, language=args.lang)
    print("AGENT:", session.open())
    try:
        while not session.closed:
            print("YOU:  ", end="")
            print("AGENT:", session.respond(input()))
    except (EOFError, KeyboardInterrupt):
        print()
        session.hang_up()
    row = get_conversation(conn, ev.conversation_id)
    keys = ("state", "outcome", "intent", "confidence", "summary", "next_action", "escalation_reason")
    print("\n--- structured outcome ---")
    print(json.dumps({k: row[k] for k in keys}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
