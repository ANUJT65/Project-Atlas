from flask import Flask
from flask_cors import CORS
from routes.jira2code_routes import jira2code_bp
from routes.jirastories import jirastories_bp
from routes.docgeneratorbrdsrs import docgeneratorbrdsrs_bp

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Register blueprints
app.register_blueprint(jira2code_bp, url_prefix='/api/jira2code')
app.register_blueprint(jirastories_bp, url_prefix='/api/jirastories')
app.register_blueprint(docgeneratorbrdsrs_bp, url_prefix='/api/docgeneratorbrdsrs')

@app.route('/')
def index():
    return {"status": "API is running"}

if __name__ == '__main__':
    app.run(debug=True, port=5000) 