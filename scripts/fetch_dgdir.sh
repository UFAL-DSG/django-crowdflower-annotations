#!/bin/bash
#
# Usage: see below or run without arguments.
# 
# This script has to be stored in the `scripts' directory directly below
# the Dialogue Transcription application's root directory.
#
# author: Matěj Korvas
# date: 2013-09-11

read -r -d '' usage <<END
Usage: $0 remote_url [unpack_command]

Fetches dialogues from a remote directory using  SCP  and  creates  a  list
suitable for import using the Import Dialogues view.

Arguments:
  remote_url ... URL of the remote file (can be a directory) to be fetched
  unpack_command ...  If the file is an archive, this should be  a  command
    to call from the import target directory  with  the  imported  file  as
    an argument to postprocess (unpack)  the  downloaded  file.   A  useful
    example is "tar xzvf".  If not  supplied,  no  postprocessing  will  be
    done.   In  either  case,  the  resulting  file  is   assumed   to   be
    a directory with dialogue log directories as its immediate children.
END

if [[ -z "$1" ]]; then
	echo "$usage"
	return 2>/dev/null || exit;
fi

# Don't go over errors.
set -e

# Read arguments.
remote_url="$1"
shift
post_cmd="$1"

# Process directory and file names.
script_dir=$(dirname $(readlink -e "$0"))
app_dir="$script_dir/../"
batch_name=$(sed -e 's/^[^:]*://' -e 's#^.*/##' -e 's/\.[^.]*$//' <<<"$remote_url")
timestamp=`date +%y-%m-%d-%H%M`
import_dir="$app_dir"data/import/$timestamp-"$batch_name"
list_fname="$app_dir"data/lists/$timestamp-"$batch_name".lst

mkdir -p "$import_dir"
mkdir -p "$app_dir"data/lists

# Download the file.
echo "Going to copy the files now. You may be asked for login credentials by scp."
scp -r "$remote_url" "$import_dir"
echo "Copying done."

# Postprocess (unpack) the file.
if [[ -n "$post_cmd" ]]; then
	echo "Going to postprocess the downloaded file."
	cd "$import_dir" && $post_cmd *
	cd "$OLDPWD"
	echo "Postprocessing done."
fi

# Create the dialogue list.
# (The directory structure now is
#			$PROJECT_DIR/data/import/`date`-$batch_name/imported_dir/dg_dirs,
#  i.e.,                              $import_dir/imported_dir/dg_dirs.)
echo "Creating the dialogue dirs list."
find "$import_dir" -mindepth 2 -maxdepth 2 -type d >"$list_fname"
echo "List created."

# # This would be needed if "$import_dir" were not an absolute path.
# import_dir_resafe=$(sed -e 's:[][\^\$*#\\]:\\&:g' <<<"$import_dir")
# 	sed -e "s#^#$import_dir_resafe/#" >"$list_fname"

# Print the final message.
echo "Dialogues have been successfully imported."
echo "The dialogue list filename (to use in the Import Dialogues view) is:"
echo "    \"$list_fname\""
