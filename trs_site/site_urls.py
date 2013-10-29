from django.conf.urls import patterns, include, url

import settings

from django.contrib import admin
admin.autodiscover()

pattern_args = [
    url(r'^admin/', include(admin.site.urls), name="admin"),
    url(r'^accounts/login/$', 'django.contrib.auth.views.login', name='login'),
]

_file_email_backend = 'django.core.mail.backends.filebased.EmailBackend'
if settings.EMAIL_BACKEND == _file_email_backend:
    pattern_args.append(
        url(r'^accounts/password_reset/done/$',
            'trs_site.views.password_reset_done',
            name='password_reset_done'))

pattern_args.extend((
    url('^accounts/', include('django.contrib.auth.urls')),
    url(r'^media/(?P<path>.*)$',
        'django.views.static.serve',
        {'document_root': settings.MEDIA_ROOT}),
    url(r'^static/(?P<path>.*)$',
        'django.views.static.serve',
        {'document_root': settings.STATIC_ROOT}),
    url(r'^', include('transcription.urls'))))

urlpatterns = patterns('', *pattern_args)
