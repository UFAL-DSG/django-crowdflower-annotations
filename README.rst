=============
Prerequisites
=============
- Python 2 (version 2.7.3 proven to work)

  ::

    # apt-get install python2.7

- Django (version 1.4.1 proven to work)

  ::

    # pip install Django==1.4.1

  *or* a newer version, such as

  ::

    # pip install Django==1.5.4

- a web server (example relevant configuration is shown for Apache 2) 
  able to handle WSGI

  ::

    # apt-get install libapache2-mod-wsgi


=========================================================
How to set up the transcription environment on the server
=========================================================
1. Update the ``localsettings.py`` config file (create this by copying 
   ``localsettings.py.example``) to suit your environment. Meaning and 
   format of all configuration variables should be clear from the comments 
   in ``localsettings.py.example``.

2. Run ``scripts/setup_script.py``.

3. Set up your webserver to find your new transcription web application.  
   For Apache, this can be done by inserting a snippet like the following to

   ::

     /etc/apache2/sites-available/default

   and

   ::

     /etc/apache2/sites-enabled/000-default

   (which is by default a symlink to the former file)
   below the root ``<VirtualHost>`` element:
 
   ::

     WSGIDaemonProcess app_transcript
     WSGIScriptAlias /apps/transcription /webapps/transcription/trs_site/wsgi.py
     <Location /apps/transcription>
       WSGIProcessGroup app_transcript
     </Location>
 
   This particular configuration would make the Apache webserver associate 
   the ``<hostname>/apps/transcription`` URL with the application directory 
   ``/webapps/transcription``, affecting where the ``wsgi.py`` script and 
   other Python modules used by the app are looked for.

4. Create the database (following is pseudocode, do *not* copy & paste it to 
   your terminal):

   ::

     cd /webapps/transcription && ./manage.py syncdb
     # You will be asked to enter your superuser details.

   Make sure the access permissions are set correctly for directories used 
   by Django.  This can mean you need to issue the following commands, 
   depending on your configured paths:
  
   ::

     # PROJECT_PATH=/webapps/transcription
     # cd $PROJECT_PATH &&\
       chown www-data db{,trss.db} data/{,conversations,import,lists} log/{curl,work}_logs
  
5. [Optional] Save the name and domain of your new site to the database.  
   The name of the site appears in password-reset emails, and defaults to 
   ``example.com``.
  
   You can change the domain and name of the site using the following 
   commands:
  
   ::

     # cd $PROJECT_PATH && ./manage.py dbshell
     SQL> UPDATE django_site SET name = '<your chosen site name>';
     SQL> UPDATE django_site SET domain = '<your site domain>';
  
6. Collect static files using the following command:
  
   ::

     $ cd $PROJECT_PATH && ./manage.py collectstatic -l

   You may be asked to confirm you want to override existing files. In 
   a clean installation, with the default setting of ``STATIC_ROOT``, this 
   warning is a false alarm. If there were static files collected, they 
   would be overwritten, but there are none.
  
7. Reload the web server, open the site URL, and log in with the superuser 
   account you created.


===========================================
How to set up transcription via Crowdflower
===========================================

1. Get yourself an account with Crowdflower (http://crowdflower.com).
  
2. Make sure ``USE_CF`` is set to ``True`` in ``localsettings.py``.  Update 
   all other related configuration, including ``CF_KEY`` (should be 
   provided by Crowdflower for your account).
  
   If you changed ``USE_CF`` or any configuration variables pointing to 
   directories or URLs, you probably have to repeat the previous part.
  
3. Create Crowdflower jobs using the `Create new Crowdflower jobs` item on 
   the main menu. Main menu is what you see when you log in to the site 
   using your web browser.
  
   When you submit the form for creating Crowdflower jobs, the 
   Transcription app will communicate with Crowdflower. You will have to 
   wait for a response for a minute or so.
  
   When successful, you will have new jobs created in your Crowdflower 
   account, and in the Transcription app's database. Dialogue prices will 
   now be associated with corresponding Crowdflower job IDs, and your 
   dialogues will be uploaded to their appropriate job based on the price.
  
   Dialogue prices are computed using the configuration variables 
   ``PRICE_CONST``, ``PRICE_PER_MIN``, and ``PRICE_PER_TURN``. If you 
   change your mind about these constants any time later, you can 
   reconfigure Django and have it recompute dialogue prices by using the 
   `Update Price` action in the `Dialogues` admin view.
   
4. Order your units through the Crowdflower web interface. You want to set 
   the price for each job the same as what the title specifies.

   **Update**: Crowdflower requires that the jobs don't specify the price 
   in their title. Therefore, you should change the title before ordering 
   the job. A good option is writing

    Dialogue transcription – price level K

   instead of

    Dialogue transcription – K0 cents.
  
5. If fully annotated transcription elements are desired also for gold 
   units, fire gold hooks (an option in the main menu) when finished with 
   the job, just in case the job_complete webhook from CrowdFlower did not 
   fire automatically.

.. TODO: update the instruction above.


=======================
How to import dialogues
=======================

1. Make the dialogue log directories available at the server's filesystem.
   If the dialogue logs are on a remote filesystem, you can use the
   ``fetch_dgdir.sh`` script (from the ``scripts`` directory) to achieve 
   this.  The script also creates a list of imported dialogues for you, so 
   you can then skip the next step.
   
   For using the ``fetch_dgdir.sh`` script, you need to:
     1. create a directory with dialogue logs as its immediate children at
        the remote filesystem;
     2. (optional) pack the directory;
     3. run the script at the target server; run the script without
        arguments for usage message.
  
2. Create a text file listing paths towards the log directories, one per 
   line (preferably in ``localsettings.LISTS_DIR``, although whether you 
   put it in this directory or elsewhere, probably has no impact).
  
3. Open the web interface of your application and navigate to dialogue 
   import (through an option in the menu at the first page after login, or 
   through the `Dialogues->Add` option of the Admin app). Specify the path 
   towards the file listing your dialogues, any other options as required, 
   and press the button. Depending on the number of dialogues imported, you 
   might have to wait a considerable amount of time until the page with an 
   import report loads.
  
   If you are using Crowdflower, you can choose to upload all imported 
   dialogues to Crowdflower right away (using the corresponding checkbox in 
   the `Import Dialogues` form) or you can do so any time later using the 
   Upload to Crowdflower action from the `Dialogues` admin page.  There, 
   you will be provided with various filters to help you specify exactly 
   the set of dialogues you wish to have annotated.
  
   Note that the CSV file you are asked to provide name for may be very 
   helpful when the transcriptions are done and you want to delete the 
   dialogue logs from the filesystem. Therefore, you should enter a name for 
   it by which you will be able to recognize what data subset it belongs to.  
   This CSV file is stored in the directory configured as 
   ``CONVERSATION_DIR``.


=================================
How to get data out of the system
=================================

There are two ways to export the data from the database Django uses 
internally:

  .. _(A):

  A) Make a database dump.

  .. _(B):

  B) Export the dialogue logs.


---------------------------
Dumping the Django database
---------------------------
`(A)`_ is done by simply running the script ``scripts/dumpdata.sh``. This 
exports the data from the Transcription app and data about the Django 
users, to the ``data/dumps`` directory in the JSON format.

This is a good option to backup your data (they can be loaded again using 
``./manage.py loaddata dump.json``) but not the right option if you want to 
further process the transcriptions. In the latter case, follow the option 
`(B)`_.


-----------------------
Exporting dialogue logs
-----------------------
`(B)`_ is done from the Admin site (`Admin` option in the main menu). See 
`How to export`_ below for details.

Before you export
~~~~~~~~~~~~~~~~~
There are two mechanisms to track workers:

A) Crowdflower webhooks

B) cookies.

Crowdflower webhooks should track workers more smartly but they do not work 
as smoothly as plain cookies. Anyway, it is good to try to take the best of 
both. The app implements two special actions for this purpose:

1. reconstructing missing worker IDs from stored cookie data

2. firing Crowdflower webhooks for gold items (which are not ever fired by 
   default).

Thus, when you are finished with a batch of transcriptions, you should run 
these two actions. The former is accessible from the Main menu as 
`Reconstruct worker IDs`, and takes some time to complete – please be 
patient waiting for the page to reload. The same applies for the latter 
action. The link's name is `Fire hooks for gold items`. This action should 
not be triggered before the formerly mentioned one, as the assignment of 
worker IDs to annotations is based on a heuristic and may be faulty.

How to export
~~~~~~~~~~~~~
Go to the Admin site (`Admin` option in the main menu) for Dialogues (click 
the link `Dialogues` at the main admin page).  Select dialogues you wish to 
export using the checkboxes left of dialogue names, possibly with the help 
of filters or the search field.  (Note also the `Select all N dialogues` 
link right of the search field if you check the checkbox in the header 
row.) From the `Action` rolldown menu, select the `Export annotations` 
option and click `Go`.  The dialogue logs with annotations will be exported 
to ``data/export``.  Check the message at the top of the page that loads 
after the export is done for the exact path to the annotated logs 
directory.

After you export
~~~~~~~~~~~~~~~~
After you have exported the data, you probably want to copy them back to 
the dialogue directories, possibly on a remote server.

Note that by exporting the data, you do *not* remove them either from the 
app's database nor from the filesystem. If you want to remove them from the 
database, choose the appropriate action from the Admin site where you 
exported them (but see the next paragraph). If you want to remove them from 
the filesystem, go ahead and remove them after you removed them from the 
Django database (otherwise, the app might be looking for them in the 
`transcribe` view, and not finding them). All the dialogue logs are stored 
in the directory configured as ``CONVERSATION_DIR``.

**BEFORE YOU REMOVE THE DATA** from the database, you might want to measure 
work done for all the annotators, unless a different awarding scheme is in 
force. Use the `Transcriptions` admin page and the `Measure work done` 
action to get a report about the amount of work done by each annotator.

You may also want to export all dialogues with transcriptions currently 
marked as gold. Do that by setting the `By gold status` filter in `Admin -> 
Dialogues` to `true`, selecting all the dialogues after filtering and 
choosing the `Export logs (annotations and audio)` action. The logs will be 
exported to ``settings.EXPORT_DIR`` (``data/export`` by default).
