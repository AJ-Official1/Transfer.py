from flask import Flask, request, send_from_directory, render_template_string
import os

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>File Transfer</title>
</head>
<body>
<h2>📤 Upload File</h2>
<form method="post" action="/upload" enctype="multipart/form-data">
<input type="file" name="file">
<input type="submit" value="Upload">
</form>

<h2>📥 Download Files</h2>
<ul>
{% for file in files %}
<li><a href="/download/{{file}}">{{file}}</a></li>
{% endfor %}
</ul>
</body>
</html>
"""

@app.route("/")
def index():
    files = os.listdir(UPLOAD_FOLDER)
    return render_template_string(HTML, files=files)

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]
    file.save(os.path.join(UPLOAD_FOLDER, file.filename))
    return "✅ File uploaded! <a href='/'>Go Back</a>"

@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
