#!/usr/bin/python

import httplib2
import pprint
import sys
import getopt
import ConfigParser

from apiclient.discovery import build
from apiclient.http import MediaFileUpload
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage

# Copy your credentials from the console
CLIENT_ID = 'clent id'
CLIENT_SECRET = 'secret'
PARENT_ID = 'parent dir id'

# Check https://developers.google.com/drive/scopes for all available scopes
OAUTH_SCOPE = 'https://www.googleapis.com/auth/drive'
# Redirect URI for installed apps
REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'


def retrieve_all_files(service):
  """Retrieve a list of File resources.

  Args:
    service: Drive API service instance.
  Returns:
    List of File resources.
  """
  result = []
  page_token = None
  while True:
    try:
      param = {}
      if page_token:
        param['pageToken'] = page_token
      files = service.files().list(**param).execute()

      result.extend(files['items'])
      page_token = files.get('nextPageToken')
      if not page_token:
        break
    except errors.HttpError, error:
      print 'An error occurred: %s' % error
      break
  return result

def print_file(service, file_id):
  """Print a file's metadata.

  Args:
    service: Drive API service instance.
    file_id: ID of the file to print metadata for.
  """
  try:
    file = service.files().get(fileId=file_id).execute()

    print 'Title: %s' % file['title']
    print 'MIME type: %s' % file['mimeType']
  except errors.HttpError, error:
    print 'An error occurred: %s' % error


def upload_file(a_uploadfile, a_update_fileId):
  # Create a credential storage object.  You pick the filename.
  storage = Storage('a_credentials_file')

  # Attempt to load existing credentials.  Null is returned if it fails.
  credentials = storage.get()

  if not credentials:
    print "request new access token"
    # Run through the OAuth flow and retrieve credentials
    flow = OAuth2WebServerFlow(CLIENT_ID, CLIENT_SECRET, OAUTH_SCOPE,
                               redirect_uri=REDIRECT_URI)
    authorize_url = flow.step1_get_authorize_url()
    print 'Go to the following link in your browser: ' + authorize_url
    code = raw_input('Enter verification code: ').strip()
    credentials = flow.step2_exchange(code)
    storage.put(credentials)

  # Create an httplib2.Http object and authorize it with our credentials
  http = httplib2.Http()
  http = credentials.authorize(http)

  drive_service = build('drive', 'v2', http=http)
  #import pdb
  #pdb.set_trace()


  # print "Insert a file"
  # media_body = MediaFileUpload(a_uploadfile, mimetype='text/plain', resumable=True)
  # body = {
  #   'title': 'test_strings.json',
  #   'description': 'Language for Beta',
  #   'mimeType': 'text/plain',
  #   'parents': [{'id':PARENT_ID}]

  # }

  # file = drive_service.files().insert(body=body, media_body=media_body).execute()
  # pprint.pprint(file)

  print "update a file"
  file = drive_service.files().get(fileId=a_update_fileId).execute()

  media_body = MediaFileUpload(a_uploadfile, mimetype='text/plain', resumable=True)
  body = {
    'title': 'test_strings.json',
    'description': 'Language for Beta',
    'mimeType': 'text/plain',
    'parents': [{'id':PARENT_ID}]
  }

  updated_file = drive_service.files().update(
          fileId=a_update_fileId,
          body=file,
          newRevision='new_revision',
          media_body=media_body).execute()
  #file = drive_service.files().insert(body=body, media_body=media_body).execute()
  pprint.pprint(file)
  #print print_file(drive_service, PARENT_ID)


def main(argv):
  config = ConfigParser.ConfigParser()
  config.read('config.ini')
  global CLIENT_ID
  global CLIENT_SECRET
  global PARENT_ID
  updateFileId = config.get('upload_language_beta', 'updateFileId')
  CLIENT_ID = config.get('upload_language_beta', 'CLIENT_ID')
  CLIENT_SECRET = config.get('upload_language_beta', 'CLIENT_SECRET')
  PARENT_ID = config.get('upload_language_beta', 'PARENT_ID')
    

  input_json_file = ''
  
  try:
      #opts, args = getopt.getopt(argv,"hi:o:",["ifile=","ofile="])
      opts, args = getopt.getopt(argv,"hi:",["input=", "updateFileId="])
  except getopt.GetoptError:
      print 'error: parse.py wrong command'
      sys.exit(2)
  for opt, arg in opts:
      if opt == '-h':
         print 'parse.py ????'
         sys.exit()
      elif opt in ("-i", "--input"):
          command = 'i'
          input_json_file = arg
      elif opt in ("--updateFileId"):
        updateFileId = arg

  if command == 'i':
      print 'input file = ' + input_json_file
      upload_file(input_json_file, updateFileId)

   
if __name__ == "__main__":
  main(sys.argv[1:])

