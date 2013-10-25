import os
import sys

# Update the Python path, then do some more imports.
_site_dir = os.path.realpath(os.path.dirname(__file__))
_project_dir = os.path.realpath(os.path.join(_site_dir, os.pardir))

if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)
if _site_dir not in sys.path:
    sys.path.insert(0, _site_dir)

import settings
# Note that the `settings' module can change what is imported as django.

os.environ["DJANGO_SETTINGS_MODULE"] = "settings"

# This application object is used by any WSGI server configured to use this
# file. This includes Django's development server, if the WSGI_APPLICATION
# setting points here.

from django.core.wsgi import get_wsgi_application
# NOTE: If the above line throws an exception, that means your version of
# Django is too old for this app. In that case, please, install Django 1.5.4
# using the following command:
# pip install Django==1.5.4

application = get_wsgi_application()
