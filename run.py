from revelatetw.__main__ import main

# The exe launches with the live mic loop on by default (same model as the documented
# `python -m revelatetw --gui --transcriber-model small`), so the header wave and mic work out of the box.
if __name__ == "__main__":
    raise SystemExit(main(["--gui", "--transcriber-model", "small"]))
