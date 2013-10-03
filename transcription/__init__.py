import os.path
import sys

# Insert this script's directory to the Python path.
SCRIPT_DIR = os.path.realpath(os.path.dirname(__file__))
sys.path.insert(0, SCRIPT_DIR)
del SCRIPT_DIR
