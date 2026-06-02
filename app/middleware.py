from flask import request

def require_api_key(f):
    def wrapper(*args, **kwargs):
        key = request.headers.get('X-API-Key')
        if not key:
            return {"error": "missing api key"}, 401
        return f(*args, **kwargs)
    return wrapper


