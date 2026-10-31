"""Developer CLI (spec §16.3): python cli.py <command> [--json-out]"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")


def _emit(data, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                print(f"{k}: {v}")
        else:
            print(data)


def cmd_validate_content(_args) -> None:
    from app.tarot_content.cards import CARDS, validate_cards
    from app.tarot_content.tags import TAGS, validate_tags
    from app.tarot_content.spreads import SPREADS, validate_spreads
    from app.seed.load_content import validate_content

    problems = validate_content()
    report = {
        "cards": len(CARDS), "tags": len(TAGS), "spreads": len(SPREADS),
        "problems": problems,
        "valid": not problems,
    }
    _emit(report, _args.json_out)
    sys.exit(0 if not problems else 1)


def _ensure_schema():
    from app.db.base import Base
    from app.db.session import get_engine
    import app.models  # noqa: F401  register mappers
    Base.metadata.create_all(get_engine())


def cmd_load_content(args) -> None:
    from app.db.session import get_session_factory
    from app.seed.load_content import load_content

    _ensure_schema()

    session = get_session_factory()()
    try:
        report = load_content(session)
        _emit({"status": "ok", **report.as_dict()}, args.json_out)
    finally:
        session.close()


def cmd_reset_user_data(args) -> None:
    from app.db.session import get_session_factory
    from app.seed.load_content import reset_user_data

    _ensure_schema()

    if args.confirm != "RESET_USER_DATA":
        print("Refusing: pass --confirm RESET_USER_DATA to perform the destructive reset.", file=sys.stderr)
        sys.exit(2)
    session = get_session_factory()()
    try:
        deleted = reset_user_data(session, confirm=args.confirm)
        _emit({"status": "reset_done", "deleted": deleted}, args.json_out)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Tarot mini app developer CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("validate-content")
    p1.set_defaults(func=cmd_validate_content)
    p2 = sub.add_parser("load-content")
    p2.set_defaults(func=cmd_load_content)
    p3 = sub.add_parser("reset-user-data")
    p3.add_argument("--confirm", default="")
    p3.set_defaults(func=cmd_reset_user_data)

    for sp in sub.choices.values():
        sp.add_argument("--json-out", action="store_true")

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
