from flask import request
import secrets
from app.middleware import require_api_key

blueprint = Blueprint('monitors', __name__)

@blueprint.route('/monitors', methods=['POST'])
def create_monitor():
    # 1. get url and slack_webhook_url from request.json
    # 2. generate an api key with secrets.token_hex(32)
    # 3. return the key for now (skip database insert)