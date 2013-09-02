from django.conf.urls.defaults import patterns, url

import settings

pattern_args = ['',
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

#                 url(r'^temp-test$',
#                     'transcription.views.temp_test',
#                     name="temp_test"),

                url(r'^',
                    'transcription.views.home',
                    name='home')
               ]
if settings.USE_CF:
    pattern_args.append(url(r'^log-work$',
                            'transcription.views.log_work',
                            name="log_work"))

urlpatterns = patterns(*pattern_args)
