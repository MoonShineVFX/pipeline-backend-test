import os
from flask import Flask, request, Blueprint, redirect
from google.cloud import storage
from datetime import datetime, timedelta
import sqlalchemy


app = Flask(__name__)
app.config['APPLICATION_ROOT'] = '/api'
bp = Blueprint('prefixbp', __name__, template_folder='templates')


@bp.route('/sql')
def sql():
    db_user = os.environ["DB_USER"]
    db_pass = os.environ["DB_PASS"]
    db_name = os.environ["DB_NAME"]
    db_socket_dir = os.environ.get("DB_SOCKET_DIR", "/cloudsql")
    cloud_sql_connection_name = os.environ["CLOUD_SQL_CONNECTION_NAME"]

    db = sqlalchemy.create_engine(
        # Equivalent URL:
        # mysql+pymysql://<db_user>:<db_pass>@/<db_name>?unix_socket=<socket_path>/<cloud_sql_instance_name>
        sqlalchemy.engine.url.URL.create(
            drivername="mysql+pymysql",
            username=db_user,  # e.g. "my-database-user"
            password=db_pass,  # e.g. "my-database-password"
            database=db_name,  # e.g. "my-database-name"
            query={
                "unix_socket": "{}/{}".format(
                    db_socket_dir,  # e.g. "/cloudsql"
                    cloud_sql_connection_name)  # i.e "<PROJECT-NAME>:<INSTANCE-REGION>:<INSTANCE-NAME>"
            }
        ),
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800
    )

    comments = []
    with db.connect() as conn:
        for row in conn.execute('SELECT * FROM entries;').fetchall():
            comments.append(dict(row))

    return {'comments': comments}


@bp.route('/')
def default():
    return 'pipeline test api'


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


@bp.route('/get-file/<path:path>')
def get_file(path):
    # Storage access
    client = storage.Client()
    bucket = client.get_bucket('image-lib')
    blob = bucket.blob(path)

    # Check exists
    if not blob.exists(client):
        return 'Object not found', 400

    # Auth for signed url
    import google.auth
    credentials, project_id = google.auth.default()
    from google.auth.transport import requests
    r = requests.Request()
    credentials.refresh(r)
    service_account_email = credentials.service_account_email

    expires = datetime.now() + timedelta(minutes=10)
    signed_url = blob.generate_signed_url(
        expiration=expires, service_account_email=service_account_email, access_token=credentials.token
    )
    return redirect(signed_url)


app.register_blueprint(bp, url_prefix='/api')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
