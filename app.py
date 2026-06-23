"""
Demo 2 — Flask application entry point.
"""

import time
from flask import Flask
from flask_cors import CORS

from routes.auth           import auth_bp
from routes.analytics      import analytics_bp
from routes.audit_trail    import audit_trail_bp
from routes.data_view      import data_view_bp
from routes.job_cards      import job_cards_bp
from routes.pages          import pages_bp
from routes.process_master import process_master_bp
from routes.quality_check  import quality_check_bp
from routes.users          import users_bp


app = Flask(__name__)
app.secret_key = "8db1cd4eca12bd711c3edd2ddf8d24d753e81fcf7e27428dfd9944d610ef1bde"
CORS(app)

app.config["TEMPLATES_AUTO_RELOAD"]  = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

app.register_blueprint(pages_bp)
app.register_blueprint(job_cards_bp)
app.register_blueprint(process_master_bp)
app.register_blueprint(quality_check_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(data_view_bp)
app.register_blueprint(audit_trail_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(users_bp)


@app.after_request
def add_no_cache_headers(response):
    if app.debug:
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, "
            "post-check=0, pre-check=0, max-age=0"
        )
        response.headers["Pragma"]  = "no-cache"
        response.headers["Expires"] = "-1"
    return response


@app.context_processor
def inject_version():
    return {"version": int(time.time())}


if __name__ == "__main__":
    app.run(
        debug=True,
        use_reloader=True,
        reloader_type="stat",
        extra_files=[
            "templates/page1.html",
            "templates/page2.html",
            "templates/page3.html",
            "templates/page4.html",
            "templates/page5.html",
            "templates/base.html",
            "static/css/base.css",
            "static/css/page1.css",
            "static/css/page2.css",
            "static/css/page3.css",
            "static/css/page5.css",
            "static/js/base.js",
            "static/js/page1.js",
            "static/js/page2.js",
            "static/js/page3.js",
            "static/js/page5.js",
            "static/js/upload.js",
        ],
        port=5000,
    )