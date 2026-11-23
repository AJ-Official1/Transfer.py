from flask import Flask, request, send_from_directory, render_template_string, redirect, url_for, flash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.secret_key = "nexus-file-transfer-secret"

UPLOAD_FOLDER = "uploads"
MAX_CONTENT_LENGTH = 100 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NEXUS | File Transfer</title>

<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Space Grotesk', sans-serif;
    background: #070b18;
    color: white;
    min-height: 100vh;
    overflow-x: hidden;
}

body::before {
    content: "";
    position: fixed;
    inset: 0;
    background-image:
        linear-gradient(rgba(0,220,255,.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,220,255,.04) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
}

.glow {
    position: fixed;
    width: 350px;
    height: 350px;
    background: #4938ff;
    filter: blur(160px);
    opacity: .22;
    top: -100px;
    right: -80px;
    pointer-events: none;
}

.container {
    width: 90%;
    max-width: 1100px;
    margin: auto;
    padding: 35px 0;
    position: relative;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 85px;
}

.logo {
    font-size: 25px;
    font-weight: 700;
    letter-spacing: 3px;
    color: #55eaff;
    text-shadow: 0 0 20px #00d9ff;
}

.status {
    color: #65ffc1;
    font-size: 12px;
    letter-spacing: 2px;
}

.status span {
    display: inline-block;
    width: 8px;
    height: 8px;
    background: #65ffc1;
    border-radius: 50%;
    margin-right: 8px;
    box-shadow: 0 0 12px #65ffc1;
}

.hero {
    margin-bottom: 45px;
}

.hero small {
    color: #55eaff;
    letter-spacing: 4px;
}

.hero h1 {
    font-size: clamp(38px, 7vw, 65px);
    line-height: 1.1;
    margin: 18px 0;
}

.hero h1 span {
    color: #55eaff;
    text-shadow: 0 0 25px rgba(85,234,255,.5);
}

.hero p {
    color: #8795b5;
    line-height: 1.8;
}

.dashboard {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 25px;
}

.card {
    background: rgba(17, 27, 51, .85);
    border: 1px solid rgba(85,234,255,.2);
    border-radius: 20px;
    padding: 28px;
    box-shadow: 0 15px 50px rgba(0,0,0,.25);
    backdrop-filter: blur(15px);
}

.card h2 {
    font-size: 19px;
    margin-bottom: 25px;
}

.upload-area {
    border: 2px dashed rgba(85,234,255,.35);
    border-radius: 15px;
    padding: 45px 15px;
    text-align: center;
    cursor: pointer;
    transition: .3s;
    background: rgba(85,234,255,.03);
}

.upload-area:hover,
.upload-area.dragover {
    border-color: #55eaff;
    background: rgba(85,234,255,.1);
    box-shadow: 0 0 25px rgba(85,234,255,.1);
}

.upload-icon {
    font-size: 45px;
    color: #55eaff;
    margin-bottom: 15px;
}

.upload-area h3 {
    font-size: 16px;
}

.upload-area p {
    color: #8795b5;
    font-size: 12px;
    margin-top: 10px;
}

input[type="file"] {
    display: none;
}

#fileName {
    color: #55eaff;
    font-size: 12px;
    margin-top: 15px;
    overflow-wrap: anywhere;
}

button {
    width: 100%;
    margin-top: 20px;
    padding: 15px;
    border: none;
    border-radius: 10px;
    background: linear-gradient(90deg, #00d9ff, #8b70ff);
    color: #07111c;
    font-weight: 700;
    font-size: 14px;
    cursor: pointer;
    transition: .3s;
}

button:hover {
    transform: translateY(-3px);
    box-shadow: 0 0 25px rgba(85,234,255,.4);
}

button:disabled {
    opacity: .4;
    cursor: not-allowed;
    transform: none;
}

.file-list {
    max-height: 350px;
    overflow-y: auto;
}

.file-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 15px;
    margin-bottom: 12px;
    background: rgba(255,255,255,.035);
    border: 1px solid rgba(85,234,255,.12);
    border-radius: 12px;
}

.file-info {
    min-width: 0;
}

.file-info strong {
    display: block;
    font-size: 13px;
    overflow-wrap: anywhere;
}

.file-info small {
    display: block;
    color: #8795b5;
    margin-top: 5px;
    font-size: 11px;
}

.download {
    flex-shrink: 0;
    text-decoration: none;
    color: #55eaff;
    border: 1px solid rgba(85,234,255,.4);
    padding: 9px 12px;
    border-radius: 8px;
    font-size: 11px;
    transition: .3s;
}

.download:hover {
    background: #55eaff;
    color: #07111c;
}

.empty {
    text-align: center;
    color: #8795b5;
    padding: 45px 10px;
}

.flash {
    background: rgba(85,234,255,.08);
    border: 1px solid rgba(85,234,255,.3);
    color: #55eaff;
    padding: 13px;
    margin-bottom: 20px;
    border-radius: 10px;
    font-size: 13px;
}

.flash.error {
    color: #ff8499;
    border-color: #ff8499;
}

footer {
    margin-top: 55px;
    text-align: center;
    color: #647391;
    font-size: 11px;
    letter-spacing: 2px;
}

@media(max-width: 750px) {
    header {
        margin-bottom: 55px;
    }

    .dashboard {
        grid-template-columns: 1fr;
    }

    .card {
        padding: 20px;
    }

    .hero h1 {
        font-size: 42px;
    }
}
</style>
</head>

<body>

<div class="glow"></div>

<div class="container">

<header>
    <div class="logo">✦ NEXUS</div>
    <div class="status">
        <span></span>SYSTEM ONLINE
    </div>
</header>

<section class="hero">
    <small>/// NEXT GENERATION FILE SHARING</small>

    <h1>
        Transfer Files<br>
        At <span>Light Speed.</span>
    </h1>

    <p>
        Welcome to NEXUS. Upload, store and download
        your files through a futuristic transfer interface.
    </p>
</section>

{% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
        <div class="flash {{ category }}">{{ message }}</div>
    {% endfor %}
{% endwith %}

<section class="dashboard">

<div class="card">

    <h2>⇧ Upload Files</h2>

    <form id="uploadForm"
          action="/upload"
          method="POST"
          enctype="multipart/form-data">

        <label class="upload-area" id="dropArea" for="fileInput">

            <div class="upload-icon">⇧</div>

            <h3>Drop files here</h3>

            <p>Click to browse your device</p>

            <div id="fileName">NO FILE SELECTED</div>

        </label>

        <input
            type="file"
            name="file"
            id="fileInput"
            required
        >

        <button type="submit" id="uploadButton" disabled>
            INITIATE TRANSFER ↗
        </button>

    </form>

</div>

<div class="card">

    <h2>▤ Available Files</h2>

    <div class="file-list">

        {% for file in files %}

        <div class="file-item">

            <div class="file-info">
                <strong>{{ file }}</strong>
                <small>{{ file_sizes[file] }}</small>
            </div>

            <a class="download"
               href="{{ url_for('download', filename=file) }}">
                DOWNLOAD ↓
            </a>

        </div>

        {% else %}

        <div class="empty">
            ◇<br><br>
            No files available yet.
        </div>

        {% endfor %}

    </div>

</div>

</section>

<footer>
    NEXUS FILE TRANSFER SYSTEM · VERSION 2.0
</footer>

</div>

<script>
const input = document.getElementById("fileInput");
const dropArea = document.getElementById("dropArea");
const fileName = document.getElementById("fileName");
const button = document.getElementById("uploadButton");

function selectFile(file) {
    if (!file) return;

    fileName.textContent = file.name;
    button.disabled = false;
}

input.addEventListener("change", function() {
    selectFile(this.files[0]);
});

["dragenter", "dragover"].forEach(function(event) {
    dropArea.addEventListener(event, function(e) {
        e.preventDefault();
        dropArea.classList.add("dragover");
    });
});

["dragleave", "drop"].forEach(function(event) {
    dropArea.addEventListener(event, function(e) {
        e.preventDefault();
        dropArea.classList.remove("dragover");
    });
});

dropArea.addEventListener("drop", function(e) {
    if (e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        selectFile(input.files[0]);
    }
});

document.getElementById("uploadForm").addEventListener("submit", function() {
    button.disabled = true;
    button.textContent = "TRANSFERRING...";
});
</script>

</body>
</html>
"""


@app.route("/")
def index():

    files = []

    for filename in os.listdir(UPLOAD_FOLDER):
        path = os.path.join(UPLOAD_FOLDER, filename)

        if os.path.isfile(path):
            files.append(filename)

    files.sort(
        key=lambda f: os.path.getmtime(
            os.path.join(UPLOAD_FOLDER, f)
        ),
        reverse=True
    )

    file_sizes = {}

    for filename in files:

        size = os.path.getsize(
            os.path.join(UPLOAD_FOLDER, filename)
        )

        if size >= 1024 * 1024:
            file_sizes[filename] = f"{size / (1024 * 1024):.2f} MB"
        else:
            file_sizes[filename] = f"{size / 1024:.2f} KB"

    return render_template_string(
        HTML,
        files=files,
        file_sizes=file_sizes
    )


@app.route("/upload", methods=["POST"])
def upload():

    uploaded_file = request.files.get("file")

    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a file first.", "error")
        return redirect(url_for("index"))

    filename = secure_filename(uploaded_file.filename)

    if not filename:
        flash("Invalid filename.", "error")
        return redirect(url_for("index"))

    uploaded_file.save(
        os.path.join(UPLOAD_FOLDER, filename)
    )

    flash("File uploaded successfully!", "success")

    return redirect(url_for("index"))


@app.route("/download/<path:filename>")
def download(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename,
        as_attachment=True
    )


@app.errorhandler(413)
def file_too_large(error):

    flash("File exceeds the 100 MB upload limit.", "error")

    return redirect(url_for("index"))


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )