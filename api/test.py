from flask import jsonify

def handler(request):
    return jsonify({"message": "Hello from Happy Solar API!"})
