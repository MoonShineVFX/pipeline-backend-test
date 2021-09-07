import os
from flask import Flask, request, Blueprint, redirect
from google.cloud import storage
import google.auth
from google.auth.transport import requests
from datetime import datetime, timedelta
import sqlalchemy


app = Flask(__name__)
app.config['APPLICATION_ROOT'] = '/api'
bp = Blueprint('prefixbp', __name__, template_folder='templates')


# Auth for signed url
def get_signed_credentials():
    credentials, project_id = google.auth.default()
    req = requests.Request()
    credentials.refresh(req)
    return credentials


# Get SQL connection
def get_SQL_db():
    db_user = os.environ["DB_USER"]
    db_pass = os.environ["DB_PASS"]
    db_name = os.environ["DB_NAME"]
    cloud_sql_connection_name = os.environ["CLOUD_SQL_CONNECTION_NAME"]

    return sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL.create(
            drivername="mysql+pymysql",
            username=db_user,  # e.g. "my-database-user"
            password=db_pass,  # e.g. "my-database-password"
            database=db_name,  # e.g. "my-database-name"
            query={
                "unix_socket": f'/cloudsql/{cloud_sql_connection_name}'
            }
        ),
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800
    )

# Define
GCS_CREDENTIALS = get_signed_credentials()
SQL_DB = get_SQL_db()


# List SQL data
@bp.route('/sql')
def sql():
    comments = []
    with SQL_DB.connect() as conn:
        for row in conn.execute('SELECT * FROM entries;').fetchall():
            comments.append(dict(row))

    return {'comments': comments}


@bp.route('/')
def default():
    return 'pipeline test api'


# Upload file to Cloud Storage
@bp.route('/upload-file', methods=['POST'])
def upload_image():
    # Storage access
    uploaded_file = request.files.get('file')
    client = storage.Client()
    bucket = client.get_bucket('image-lib')

    # Create a new blob and upload the file's content.
    blob = bucket.blob(uploaded_file.filename)
    blob.upload_from_string(
        uploaded_file.read(),
        content_type=uploaded_file.content_type
    )
    return 'OK'


# Get file from Cloud Storage with signed url
@bp.route('/get-file/<path:path>')
def get_file(path):
    # Storage access
    client = storage.Client()
    bucket = client.get_bucket('image-lib')
    blob = bucket.blob(path)

    # Check exists
    if not blob.exists(client):
        return 'Object not found', 400

    # Generate signed url
    expires = datetime.now() + timedelta(minutes=10)
    signed_url = blob.generate_signed_url(
        expiration=expires,
        service_account_email=GCS_CREDENTIALS.service_account_email,
        access_token=GCS_CREDENTIALS.token
    )
    return redirect(signed_url)


app.register_blueprint(bp, url_prefix='/api')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
