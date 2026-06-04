from flask import request, Blueprint
import secrets
from app.middleware import require_api_key

blueprint = Blueprint('monitors', __name__)

@blueprint.route('/monitors', methods=['POST'])
def create_monitor():
    data = request.json
    url = data["url"]
    slack_webhook_url = data["slack_webhook_url"]
    api_key = secrets.token_hex(32)
    return {"api_key": api_key}