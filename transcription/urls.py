from django.conf.urls.defaults import patterns, url

import settings

urlpatterns = patterns('',
                       url(r'^transcribe$',
                           'transcription.views.transcribe',
                           name='transcribe'),

                       url(r'^data/recs/(?P<path>.*)$',
                           'django.views.static.serve',
                           {'document_root': settings.CONVERSATION_DIR}),

                       url(r'^finished$',
                           'transcription.views.finished',
                           name="finished"),

                       url(r'^import$',
                           'transcription.views.import_dialogues',
                           name="import_dialogues"),

#                        url(r'^temp-test$',
#                            'transcription.views.temp_test',
#                            name="temp_test"),

                       url(r'^log-work$',
                           'transcription.views.log_work',
                           name="log_work"),

                       url(r'^',
                           'transcription.views.home',
                           name='home')
              )
