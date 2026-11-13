"""Start RevelateTW Lite:  python lite\\run_lite.py   (or double click run_lite.bat)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from revelatelite.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
