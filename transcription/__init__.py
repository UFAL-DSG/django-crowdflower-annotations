import os.path
import sys

# Insert this script's directory to the Python path.
APP_DIR = os.path.realpath(os.path.dirname(__file__))
sys.path.insert(0, APP_DIR)
del APP_DIR
