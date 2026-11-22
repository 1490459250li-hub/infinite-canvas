# -*- coding: utf-8 -*-
import pathlib, traceback, sys
HERE = pathlib.Path(__file__).resolve().parent


def run():
    from snap_splash_impl import main
    main()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        (HERE / "err.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
