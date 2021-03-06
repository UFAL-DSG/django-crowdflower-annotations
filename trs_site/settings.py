import imp
import os
import os.path
import sys

# Set defaults before importing localsettings.
CF_WAIT_SECS = 1
CF_MAX_WAITS = 30

# TODO Check that all required config variables have been hereby imported.
from localsettings import *
import localsettings

####################
# custom variables #
####################

# Adjust Python path to include both PROJECT_DIR and SITE_DIR.
_module = sys.modules[__name__]
SITE_DIR = os.path.realpath(os.path.dirname(__file__))
PROJECT_DIR = os.path.realpath(os.path.join(SITE_DIR, os.pardir))
try:
    sys.path.append(PYLIBS_DIR)
except NameError:
    pass
if not PROJECT_DIR in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if not SITE_DIR in sys.path:
    sys.path.insert(0, SITE_DIR)

# Determine DJANGO_PATH, unless overriden by localsettings.
if not hasattr(_module, 'DJANGO_PATH'):
    if 'django' in sys.modules:
        DJANGO_PATH = os.path.dirname(sys.modules['django'].__file__)
    else:
        django_fp = django_desc = None
        try:
            django_fp, DJANGO_PATH, django_desc = imp.find_module('django')
        except Exception as ex:
            raise Exception('The Django package was not found.')
        finally:
            if django_fp is not None:
                django_fp.close()
                raise Exception('The `django\' module does not import as a '
                                '*package*.')
            del django_fp, django_desc
# Set this Django as the default django for imports.
sys.path.insert(0, os.path.join(DJANGO_PATH, os.pardir))

# Check that all configuration variables needed for Crowdflower have been set
# unless USE_CF is False.
_cf_required = ('CF_KEY', 'PRICE_CONST', 'PRICE_PER_MIN', 'PRICE_PER_TURN',
                'CODE_LENGTH', 'CODE_LENGTH_EXT', 'WORKLOGS_DIR', 'LOG_CURL')
for name in _cf_required:
    try:
        setattr(_module, name, getattr(localsettings, name))
    except AttributeError as er:
        if USE_CF:
            raise er
try:
    setattr(_module, 'CURLLOGS_DIR', localsettings.CURLLOGS_DIR)
except AttributeError as er:
    if USE_CF and LOG_CURL:
        raise er

# Other interpretation of localsettings.
TRANSCRIBE_EXTRA_CONTEXT['EXTRA_QUESTIONS'] = EXTRA_QUESTIONS
CONVERSATION_DIR = os.path.realpath(CONVERSATION_DIR)

# Settings that don't need be adapted site by site.
TRANSCRIBER_ID_COOKIE = 'transcriber_id'
TRANSCRIBER_ID_ATTR = 'trser_cookie_id'

####################################################
# Django settings for the `transcription' project. #
####################################################
TEMPLATE_DEBUG = DEBUG

MANAGERS = ADMINS

if not hasattr(_module, 'DATABASES'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3', # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
            'NAME': os.path.join(PROJECT_DIR, 'db', 'trss.db'),                      # Or path to database file if using sqlite3.
            'USER': '',                      # Not used with sqlite3.
            'PASSWORD': '',                  # Not used with sqlite3.
            'HOST': '',                      # Set to empty string for localhost. Not used with sqlite3.
            'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
        }
    }

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale
USE_L10N = True

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
MEDIA_ROOT = os.path.join(PROJECT_DIR, 'media')

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = APP_PATH + '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = os.path.join(PROJECT_DIR, 'static')

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = APP_PATH + '/static/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    '/'.join((DJANGO_PATH.replace('\\', '/'), 'contrib', 'admin', 'static')),
    PROJECT_DIR.replace('\\', '/') + '/transcription/static',
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

ROOT_URLCONF = 'site_urls'

TEMPLATE_DIRS = (
    os.path.join(PROJECT_DIR, "templates").replace('\\', '/'),
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    os.path.join(PROJECT_DIR, "transcription/templates").replace('\\', '/'),
    os.path.join(DJANGO_PATH,
                 "contrib/admin/templates/admin").replace('\\', '/'),
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',
    "transcription",
    # "django_evolution"
)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
    }
}

from django.conf.global_settings import TEMPLATE_CONTEXT_PROCESSORS
TEMPLATE_CONTEXT_PROCESSORS += ("transcription.context_processors.config_vars",
                                "transcription.context_processors.trs_stats", )

WSGI_APPLICATION = "trs_site.wsgi.application"
SUB_SITE = APP_PATH
# FORCE_SCRIPT_NAME = "/transcription"
LOGIN_URL = APP_PATH + "/accounts/login/"
# LOGIN_URL = "/accounts/login/"
# STATICFILES_STORAGE = APP_PATH
LOGIN_REDIRECT_URL = SUB_SITE


class SettingsException(Exception):
    pass
