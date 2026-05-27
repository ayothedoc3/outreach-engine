"""Background worker: processes due messages and polls for replies on a loop.

In DRY_RUN it marks due messages as drafted (so the dashboard fills with
review-ready emails). Live, it sends within the configured window and caps,
then checks mailboxes for replies. Run as the `worker` process (see Procfile).
"""
from __future__ import annotations

import time

import db
import replies
import sequencer
from config import settings

LOOP_SECONDS = 300  # 5 minutes


def main() -> None:
    print(f"[worker] starting. dry_run={settings.dry_run} mailboxes={len(settings.mailboxes)} model={settings.model}")
    if settings.database_url:
        try:
            db.init_db()
        except Exception as e:  # noqa: BLE001
            print(f"[worker] init_db failed: {e}")

    tick = 0
    while True:
        tick += 1
        try:
            summary = sequencer.process_due()
            if summary["processed"]:
                print(f"[worker] tick {tick}: {summary}")
        except Exception as e:  # noqa: BLE001
            print(f"[worker] process_due error: {e}")

        # poll replies every other tick when mailboxes are configured
        if settings.mailboxes and tick % 2 == 0:
            try:
                print(f"[worker] replies: {replies.poll_replies()}")
            except Exception as e:  # noqa: BLE001
                print(f"[worker] poll_replies error: {e}")

        time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    main()
