#!/usr/local/bin/python
"""Backend container entry point (ADR-011).

/data is a bind mount: Docker creates it on the host as root, and that mount
shadows the ownership baked into the image. A container starting directly as an
unprivileged user therefore cannot create the database.

This script starts as root only long enough to fix /data up, then permanently
drops its privileges before running the command. The process serving traffic is
never root.

Written in Python rather than shell so the image needs neither gosu nor su-exec:
the interpreter is already there.
"""

import os
import pwd
import sys
from pathlib import Path

APP_USER = "awtrixng-mgr"


def own_tree(root: Path, uid: int, gid: int) -> None:
    """Give the directory and its contents to the application user.

    Only entries whose ownership is already wrong are touched, so the next
    restart has nothing left to do.
    """
    for path in [root, *root.rglob("*")]:
        try:
            info = path.lstat()
            if info.st_uid != uid or info.st_gid != gid:
                os.chown(path, uid, gid, follow_symlinks=False)
        except OSError as exc:
            print(f"entrypoint: cannot adjust {path}: {exc}", file=sys.stderr)


def drop_privileges(entry: pwd.struct_passwd) -> None:
    # setuid last: it removes the right to do the other two.
    os.initgroups(entry.pw_name, entry.pw_gid)
    os.setgid(entry.pw_gid)
    os.setuid(entry.pw_uid)
    os.environ["HOME"] = entry.pw_dir
    os.environ["USER"] = entry.pw_name


def main(argv: list[str]) -> None:
    if not argv:
        print("entrypoint: no command to run", file=sys.stderr)
        raise SystemExit(2)

    data_dir = Path(os.environ.get("AWTRIXNG_DATA_DIR", "/data"))

    # Create the directory before deciding anything: it can be missing both as
    # root and with a "user:" override in compose.
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # the access check below will produce a useful message

    if os.geteuid() == 0:
        entry = pwd.getpwnam(APP_USER)
        own_tree(data_dir, entry.pw_uid, entry.pw_gid)
        drop_privileges(entry)

    if not os.access(data_dir, os.W_OK | os.X_OK):
        print(
            f"entrypoint: {data_dir} is not writable by uid {os.geteuid()}.\n"
            f"  If you override \"user:\" in docker-compose.yml, give that user "
            f"ownership of the data directory on the host.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    os.execvp(argv[0], argv)


if __name__ == "__main__":
    main(sys.argv[1:])
