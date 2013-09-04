import os
from localsettings import *
import localsettings
import sys

# custom variables
_module = sys.modules[__name__]
PROJECT_DIR = os.path.join(os.path.realpath(os.path.dirname(__file__)), '..')
if not PROJECT_DIR in sys.path:
    sys.path.append(PROJECT_DIR)
sys.path.append(PYLIBS_DIR)

CONVERSATION_DIR = localsettings.CONVERSATION_DIR
SESSION_FNAME = localsettings.SESSION_FNAME

CODE_LENGTH = localsettings.CODE_LENGTH
CODE_LENGTH_EXT = localsettings.CODE_LENGTH_EXT

USE_CF = localsettings.USE_CF
for name in ('CF_URL_START', 'CF_KEY', 'PRICE_CONST', 'PRICE_PER_MIN',
             'PRICE_PER_TURN'):
    try:
        setattr(_module, name, getattr(localsettings, name))
    except AttributeError as er:
        if USE_CF:
            raise er
# For the CF_JOB_ID and CF_JOB_IDS configuration variables, if USE_CF is in
# force, at least one of them has to be set.
_cf_ids_set = False
for name in ('CF_JOB_IDS', 'CF_JOB_ID'):
    try:
        setattr(_module, name, getattr(localsettings, name))
    except AttributeError as er:
        pass
    else:
        _cf_ids_set = True
if USE_CF and not _cf_ids_set:
    raise AttributeError('USE_CF == True but neither CF_JOB_IDS or CF_JOB_ID '
                         'is set.')
del _cf_ids_set

MAX_CHAR_ER = localsettings.MAX_CHAR_ER

XML_COMMON = localsettings.XML_COMMON
XML_SCHEMES = localsettings.XML_SCHEMES
# XML_USERTURN_PATH = localsettings.XML_USERTURN_PATH
# XML_SYSTURN_PATH = localsettings.XML_SYSTURN_PATH
# XML_TURNNUMBER_ATTR = localsettings.XML_TURNNUMBER_ATTR
# XML_REC_SUBPATH = localsettings.XML_REC_SUBPATH
# XML_REC_FNAME_ATTR = localsettings.XML_REC_FNAME_ATTR
# XML_SYSTEXT_SUBPATH = localsettings.XML_SYSTEXT_SUBPATH
# XML_TRANSCRIPTIONS_BEFORE = localsettings.XML_TRANSCRIPTIONS_BEFORE
# XML_TRANSCRIPTIONS_ELEM = localsettings.XML_TRANSCRIPTIONS_ELEM
# XML_TRANSCRIPTION_BEFORE = localsettings.XML_TRANSCRIPTION_BEFORE
# XML_TRANSCRIPTION_ELEM = localsettings.XML_TRANSCRIPTION_ELEM
# XML_AUTHOR_ATTR = localsettings.XML_AUTHOR_ATTR
# XML_DATE_ATTR = localsettings.XML_DATE_ATTR
# XML_DATE_FORMAT = localsettings.XML_DATE_FORMAT

# Django settings for the `transcription' project.

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    # ('Your Name', 'your_email@example.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3', # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': os.path.join(PROJECT_DIR, 'db/cf_trss.db'),                      # Or path to database file if using sqlite3.
#         'NAME': '/tmp/cf_trss.db',
        'USER': '',                      # Not used with sqlite3.
        'PASSWORD': '',                  # Not used with sqlite3.
        'HOST': '',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    }
}

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'Europe/Prague'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-gb'

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
ADMIN_MEDIA_ROOT = '/webapps/libs/django-1.4.1/django/contrib/admin/static/'
# ADMIN_MEDIA_ROOT = os.path.join(PROJECT_DIR, 'static')

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = '/apps/cir_transcription/media/'
# MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = os.path.join(PROJECT_DIR, 'static')

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '/apps/cir_transcription/static/'
# STATIC_URL = '/static/'
# STATIC_ROOT = STATIC_URL = '/cf_transcription/static/'

# URL prefix for admin static files -- CSS, JavaScript and images.
# Make sure to use a trailing slash.
# Examples: "http://foo.com/static/admin/", "/static/admin/".
ADMIN_MEDIA_PREFIX = '/apps/cir_transcription/static/admin/'
# ADMIN_MEDIA_PREFIX = '/static/admin/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
# 	"/webapps/cir_transcription/libs/django-1.4.1/django/contrib/admin/static",
    '/webapps/libs/django-1.4.1/django/contrib/admin/static/'
	# "/home/matej/wc/vys/cf_transcription/libs/django-1.4.1/django/contrib/admin/static",
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = '9fv=(fe8%h0&67(-$4347=iwhlpn52$o=56h&*)*!2w-5tbwt_'

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

# ROOT_URLCONF = 'transcription.urls'
ROOT_URLCONF = 'urls'

TEMPLATE_DIRS = (
#     "/home/matej/wc/vys/cf_transcription/templates",
    os.path.join(PROJECT_DIR, "templates"),
#     "/home/matej/wc/vys/cf_transcription/libs/django-1.4.1/django/contrib/auth/templates/",
#     "/home/matej/wc/vys/cf_transcription/libs/django-1.4.1/django/contrib/admin/templates/",
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',
    "transcription"
)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
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

WSGI_APPLICATION = "transcription.wsgi.application"
SUB_SITE="/apps/cir_transcription/"
#FORCE_SCRIPT_NAME="/er"
LOGIN_URL="/apps/cir_transcription/accounts/login/"
# LOGIN_URL="/accounts/login/"
# STATICFILES_STORAGE="/apps/cir_transcription"
LOGIN_REDIRECT_URL=SUB_SITE
