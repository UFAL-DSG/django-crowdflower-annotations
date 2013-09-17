from django.conf.urls.defaults import patterns, include, url
from django.contrib.auth import views as auth_views

import settings

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'^admin/', include(admin.site.urls), name="admin"),
    url(r'^accounts/logout/$', auth_views.logout, name="logout"),
    url(r'^accounts/login/$', auth_views.login, name="login"),
    url(r'^media/(?P<path>.*)$',
        'django.views.static.serve',
        {'document_root': settings.MEDIA_ROOT}),
    url(r'^static/(?P<path>.*)$',
        'django.views.static.serve',
        {'document_root': settings.STATIC_ROOT}),
    url(r'^', include('transcription.urls')),
)
