import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "transcription.settings")

# This application object is used by any WSGI server configured to use this
# file. This includes Django's development server, if the WSGI_APPLICATION
# setting points here.

# try:
from django.core.wsgi import get_wsgi_application
# # In the Ubuntu-provided package, the django.core.wsgi module is not available.
# except ImportError:
#     # In that case, do what get_wsgi_application implements in current versions
#     # of Django.
#     from django.core.handlers.wsgi import WSGIHandler
#     get_wsgi_application = lambda: WSGIHandler()

application = get_wsgi_application()
