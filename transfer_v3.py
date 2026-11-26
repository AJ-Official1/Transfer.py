import os
import re
import json
import uuid
import time
import hmac
import hashlib
import secrets
from pathlib import Path
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from flask import (
    Flask, request, jsonify, render_template_string,
    send_file, abort, session, redirect
)

# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
STORAGE = BASE_DIR / "secure_storage"
GROUP_STORAGE = STORAGE / "groups"
TEAM_FILES = STORAGE / "team_files"
LOGIN_STORAGE = BASE_DIR / "login details"

for folder in (STORAGE, GROUP_STORAGE, TEAM_FILES, LOGIN_STORAGE):
    folder.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_MEMBERS = 20

app = Flask(__name__)

# Keep the session signing key stable between server restarts.
configured_secret = os.environ.get("FLASK_SECRET_KEY")
secret_key_file = LOGIN_STORAGE / ".flask_secret_key"
if configured_secret:
    app.secret_key = configured_secret
else:
    try:
        app.secret_key = secret_key_file.read_text(encoding="utf-8").strip()
        if not app.secret_key:
            raise ValueError("Empty session secret")
    except (OSError, ValueError):
        app.secret_key = secrets.token_hex(32)
        secret_key_file.write_text(app.secret_key, encoding="utf-8")

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE + 16
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# ==========================================
# HELPERS
# ==========================================

def user_id():
    # Every private account action is tied to an authenticated account.
    return session.get("user_id")


def account_path(account_id):
    if not valid_id(account_id):
        return None
    return LOGIN_STORAGE / f"{account_id}.json"


def read_account(account_id):
    path = account_path(account_id)
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def find_account(identifier):
    identifier = identifier.strip().casefold()
    for path in LOGIN_STORAGE.glob("*.json"):
        try:
            account = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (account.get("email", "").casefold() == identifier or
                account.get("username", "").casefold() == identifier):
            return account
    return None


def valid_id(value):
    return bool(re.fullmatch(r"[a-f0-9]{32}", value or ""))


def group_path(group_id):
    return GROUP_STORAGE / f"{group_id}.json"


def file_path(file_id):
    return STORAGE / f"{file_id}.bin"


def team_file_path(file_id):
    return TEAM_FILES / f"{file_id}.bin"


def read_group(group_id):
    if not valid_id(group_id):
        return None
    path = group_path(group_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_group(group):
    group_path(group["id"]).write_text(
        json.dumps(group), encoding="utf-8"
    )


def invite_hash(code, salt):
    return hashlib.scrypt(
        code.encode("utf-8"),
        salt=bytes.fromhex(salt),
        n=2**14,
        r=8,
        p=1,
        dklen=32
    ).hex()


def is_member(group):
    return user_id() in group["members"]


def require_member(group_id):
    group = read_group(group_id)
    if not group or not is_member(group):
        abort(403)
    return group


# ==========================================
# HOME PAGE
# ==========================================


AUTH_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#170d29">
<title>SUPERIOR TRANSFER | Account</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;display:grid;place-items:center;padding:20px;font-family:Inter,sans-serif;color:white;background:radial-gradient(ellipse at 10% 15%,#843aa2 0%,transparent 42%),radial-gradient(ellipse at 85% 20%,#43277d 0%,transparent 45%),linear-gradient(135deg,#170d29,#24113b,#100b23)}
.auth-card{width:100%;max-width:440px;padding:34px;background:rgba(9,5,20,.94);border:1px solid rgba(255,255,255,.1);border-radius:16px;box-shadow:0 25px 80px rgba(0,0,0,.45)}
.brand{text-align:center;font-size:20px;font-weight:700;letter-spacing:1px;background:linear-gradient(90deg,#ff19b5,#b45aff);-webkit-background-clip:text;background-clip:text;color:transparent;margin-bottom:10px}
.subtitle{text-align:center;color:#bdb0ca;font-size:13px;margin-bottom:24px}
.tabs{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:22px}
.tabs button{padding:12px;border:1px solid rgba(255,255,255,.12);border-radius:7px;background:transparent;color:#c8bad6;font-weight:700;cursor:pointer}
.tabs button.active{background:rgba(190,70,255,.2);border-color:#bd65f5;color:white}
h1{font-size:22px;color:#e9a1ff;margin-bottom:18px}
.field{width:100%;padding:14px;margin-bottom:13px;border-radius:7px;border:1px solid rgba(255,255,255,.17);outline:none;background:#21152f;color:white;font-family:inherit;font-size:13px}
.field:focus{border-color:#c15aff;box-shadow:0 0 12px rgba(190,70,255,.15)}
.field::placeholder{color:#8e809e}
.submit{width:100%;padding:15px;margin-top:8px;background:linear-gradient(90deg,#d84aff,#9255ff);color:white;border:0;border-radius:7px;font-size:13px;font-weight:700;cursor:pointer}
.status{min-height:20px;margin-top:14px;color:#dda3ff;font-size:12px;line-height:1.6}
.note{margin-top:16px;color:#8e809e;font-size:11px;line-height:1.6;text-align:center}
</style>
</head>
<body>
<div class="auth-card">
  <div class="brand">SUPERIOR TRANSFER</div>
  <p class="subtitle">Secure file sharing starts with your account</p>
  <div class="tabs">
    <button id="loginTab" class="active" type="button" onclick="showAuth('login')">LOG IN</button>
    <button id="signupTab" type="button" onclick="showAuth('signup')">SIGN UP</button>
  </div>
  <section id="loginPanel">
    <h1>Welcome back</h1>
    <form onsubmit="submitLogin(event)">
      <input class="field" id="loginIdentifier" placeholder="Username or email" autocomplete="username" required>
      <input class="field" id="loginPassword" type="password" placeholder="Password" autocomplete="current-password" required>
      <button class="submit" type="submit">LOG IN</button>
    </form>
  </section>
  <section id="signupPanel" hidden>
    <h1>Create your account</h1>
    <form onsubmit="submitSignup(event)">
      <input class="field" id="signupUsername" placeholder="Username" minlength="3" maxlength="30" autocomplete="username" required>
      <input class="field" id="signupEmail" type="email" placeholder="Email address" maxlength="254" autocomplete="email" required>
      <input class="field" id="signupPassword" type="password" placeholder="Create password (at least 8 characters)" minlength="8" autocomplete="new-password" required>
      <button class="submit" type="submit">CREATE ACCOUNT</button>
    </form>
  </section>
  <div class="status" id="authStatus" role="status"></div>
  <p class="note">Your password is stored as a secure hash, not as readable text.</p>
</div>
<script>
function showAuth(mode){
  const login=mode==="login";
  document.getElementById("loginPanel").hidden=!login;
  document.getElementById("signupPanel").hidden=login;
  document.getElementById("loginTab").classList.toggle("active",login);
  document.getElementById("signupTab").classList.toggle("active",!login);
  document.getElementById("authStatus").textContent="";
}
async function sendAuth(url,payload){
  const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),credentials:"same-origin"});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||"Unable to complete request.");
  location.href="/";
}
async function submitLogin(event){
  event.preventDefault();
  const status=document.getElementById("authStatus");
  status.textContent="Signing in...";
  try{await sendAuth("/api/auth/login",{identifier:document.getElementById("loginIdentifier").value,password:document.getElementById("loginPassword").value});}
  catch(error){status.textContent=error.message;}
}
async function submitSignup(event){
  event.preventDefault();
  const status=document.getElementById("authStatus");
  status.textContent="Creating your account...";
  try{await sendAuth("/api/auth/register",{username:document.getElementById("signupUsername").value,email:document.getElementById("signupEmail").value,password:document.getElementById("signupPassword").value});}
  catch(error){status.textContent=error.message;}
}
</script>
</body>
</html>
"""

HOME_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#170d29">
<title>SUPERIOR TRANSFER</title>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>
* {
    margin:0;
    padding:0;
    box-sizing:border-box;
}

body {
    min-height:100vh;
    font-family:Inter,sans-serif;
    color:white;
    background:
        radial-gradient(ellipse at 10% 15%,#843aa2 0%,transparent 42%),
        radial-gradient(ellipse at 85% 20%,#43277d 0%,transparent 45%),
        radial-gradient(ellipse at 50% 100%,#a64b9c 0%,transparent 48%),
        linear-gradient(135deg,#170d29,#24113b,#100b23);
    background-attachment:fixed;
}

body::before {
    content:"";
    position:fixed;
    inset:0;
    pointer-events:none;
    background-image:
        radial-gradient(2px 2px at 20% 30%,white,transparent),
        radial-gradient(2px 2px at 70% 20%,white,transparent),
        radial-gradient(1px 1px at 40% 80%,white,transparent),
        radial-gradient(2px 2px at 90% 70%,white,transparent);
    background-size:180px 180px;
    opacity:.4;
}

.page {
    width:100%;
    min-height:100vh;
    padding:35px 15px;
    position:relative;
    z-index:1;
}

.navbar {
    width:100%;
    max-width:1120px;
    margin:0 auto 22px;
    padding:10px 14px;
    min-height:54px;
    background:rgba(8,13,23,.96);
    border-top:2px solid rgba(157,177,205,.16);
    border-bottom:1px solid rgba(157,177,205,.12);
    display:flex;
    align-items:center;
    justify-content:flex-start;
    gap:20px;
}

.brand {
    display:flex;
    align-items:center;
    gap:10px;
    flex:0 0 auto;
    color:#aebed3;
    font-size:13px;
    font-weight:600;
    letter-spacing:.1px;
    white-space:nowrap;
}

.brand-menu {
    color:#aebed3;
    font-size:17px;
    line-height:1;
}

.nav-links {
    display:flex;
    align-items:center;
    justify-content:flex-start;
    flex-wrap:wrap;
    gap:12px;
}

.nav-btn {
    padding:9px 16px;
    border:1px solid transparent;
    border-radius:5px;
    color:#aebed3;
    background:transparent;
    font-size:13px;
    font-weight:500;
    cursor:pointer;
    transition:background .18s,color .18s;
}

.nav-btn:hover {
    color:white;
    background:rgba(255,255,255,.07);
}

.nav-btn.active {
    color:white;
    background:#ed008c;
    border-color:#ed008c;
}

.profile-page {
    width:100%;
    max-width:1120px;
    margin:35px auto;
    position:relative;
    z-index:1;
}

.profile-card {
    max-width:620px;
    margin:0 auto;
    padding:30px;
    border-radius:14px;
    background:rgba(9,5,20,.88);
    border:1px solid rgba(255,255,255,.10);
    box-shadow:0 18px 50px rgba(0,0,0,.18);
}

.profile-card h1 {font-size:25px;margin-bottom:8px;}
.profile-description {color:#b9a9c8;font-size:14px;margin-bottom:25px;}
.profile-menu {display:flex;flex-direction:column;gap:10px;}
.profile-menu-item {
    width:100%;
    display:flex;
    flex-direction:column;
    align-items:flex-start;
    gap:8px;
    padding:17px 18px;
    border:1px solid rgba(255,255,255,.10);
    border-radius:9px;
    background:rgba(255,255,255,.045);
    color:#fff;
    text-align:left;
    font:inherit;
}
.profile-menu-label {font-size:10px;letter-spacing:1px;color:#b9a9c8;}
.profile-logout {
    flex-direction:row;
    justify-content:space-between;
    align-items:center;
    cursor:pointer;
    color:#ff8acb;
}
.profile-logout:hover {background:rgba(190,70,255,.14);border-color:rgba(210,110,255,.3);}

.container {
    width:100%;
    max-width:1120px;
    min-height:480px;
    margin:auto;
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:45px;
    padding:48px;
    background:rgba(9,5,20,.91);
    border:1px solid rgba(255,255,255,.08);
    border-radius:17px;
    box-shadow:0 25px 100px rgba(0,0,0,.45);
    backdrop-filter:blur(25px);
}

.upload-section {
    min-height:380px;
    border:2px dashed rgba(255,255,255,.75);
    border-radius:15px;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    padding:25px;
    text-align:center;
    transition:.3s;
}

.upload-section.dragover {
    border-color:#ed62ff;
    background:rgba(200,70,255,.1);
}

.browse-btn {
    display:inline-block;
    padding:14px 25px;
    border-radius:7px;
    background:#d9baff;
    color:#160b27;
    font-size:15px;
    font-weight:600;
    cursor:pointer;
    transition:.3s;
}

.browse-btn:hover {
    background:#f0d8ff;
    transform:translateY(-2px);
    box-shadow:0 0 25px #b45cff;
}

#fileInput,#teamFile {
    display:none;
}

.drag-text {
    margin-top:20px;
    font-size:14px;
    color:#ded4ec;
}

.file-name {
    margin-top:18px;
    font-size:12px;
    color:#e5a7ff;
    overflow-wrap:anywhere;
}

.limit {
    margin-top:auto;
    padding-top:45px;
    color:#82788f;
    font-size:12px;
}

.info-section {
    padding-top:8px;
}

h1 {
    font-size:clamp(27px,3.5vw,36px);
    line-height:1.3;
    margin-bottom:18px;
    background:linear-gradient(90deg,#ff00a8,#b340ff,#d47aff);
    -webkit-background-clip:text;
    background-clip:text;
    color:transparent;
}

.description {
    font-size:15px;
    line-height:1.8;
    color:#e0d9e9;
}

.description strong {
    color:white;
    text-decoration:underline;
}

.primary-btn {
    width:100%;
    padding:15px;
    margin-top:22px;
    background:linear-gradient(90deg,#d84aff,#9255ff);
    color:white;
    border:0;
    border-radius:7px;
    font-size:13px;
    font-weight:700;
    cursor:pointer;
    transition:.3s;
}

.primary-btn:hover:not(:disabled) {
    box-shadow:0 0 25px rgba(215,65,255,.4);
    transform:translateY(-2px);
}

.primary-btn:disabled {
    opacity:.4;
    cursor:not-allowed;
}

.progress {
    display:none;
    height:6px;
    background:#30223c;
    border-radius:20px;
    overflow:hidden;
    margin-top:18px;
}

.progress-bar {
    height:100%;
    width:0;
    background:linear-gradient(90deg,#ff31c8,#a65aff);
}

.status {
    color:#dca4ff;
    font-size:12px;
    margin-top:10px;
}

.result {
    display:none;
    margin-top:20px;
    padding:15px;
    border:1px solid rgba(100,255,190,.3);
    background:rgba(100,255,190,.06);
    border-radius:9px;
}

.result h3 {
    font-size:13px;
    color:#82ffc9;
}

.share-link {
    width:100%;
    margin-top:10px;
    padding:10px;
    border:1px solid rgba(255,255,255,.15);
    border-radius:6px;
    background:rgba(0,0,0,.3);
    color:white;
    font-size:10px;
}

.copy-btn {
    width:100%;
    margin-top:10px;
    padding:11px;
    border:0;
    border-radius:6px;
    background:#d9baff;
    color:#170d24;
    font-weight:700;
    cursor:pointer;
}

.archive {
    max-width:1120px;
    margin:22px auto;
    padding:24px;
    border-radius:14px;
    background:rgba(9,5,20,.87);
    border:1px solid rgba(255,255,255,.08);
}

.archive h2 {
    font-size:15px;
    color:#e8a0ff;
    margin-bottom:15px;
}

.archive-item {
    display:flex;
    justify-content:space-between;
    gap:15px;
    padding:12px 0;
    border-bottom:1px solid rgba(255,255,255,.08);
    color:#c7bdd2;
    font-size:12px;
}

.archive-item small {
    color:#92879f;
}

/* ==================================
   TEAM PAGE
================================== */

.team-page {
    max-width:1120px;
    margin:auto;
    display:none;
}

.team-heading {
    padding:32px;
    background:rgba(9,5,20,.91);
    border:1px solid rgba(255,255,255,.08);
    border-radius:14px;
    margin-bottom:22px;
}

.team-heading h1 {
    margin-bottom:10px;
}

.team-heading p {
    color:#bdb0ca;
    font-size:14px;
    line-height:1.8;
}

.team-grid {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:20px;
}

.team-card {
    background:rgba(9,5,20,.92);
    border:1px solid rgba(255,255,255,.1);
    border-radius:14px;
    padding:27px;
}

.team-card h2 {
    font-size:17px;
    color:#e9a1ff;
    margin-bottom:12px;
}

.team-card p {
    color:#a99db7;
    font-size:12px;
    line-height:1.8;
    margin-bottom:20px;
}

.field {
    width:100%;
    padding:14px;
    margin-bottom:13px;
    border-radius:7px;
    border:1px solid rgba(255,255,255,.17);
    outline:none;
    background:#21152f;
    color:white;
    font-family:inherit;
    font-size:13px;
}

.field:focus {
    border-color:#c15aff;
    box-shadow:0 0 12px rgba(190,70,255,.15);
}

.field::placeholder {
    color:#8e809e;
}

.team-status {
    font-size:12px;
    color:#dda3ff;
    margin-top:13px;
    line-height:1.6;
}

.group-list {
    margin-top:22px;
    background:rgba(9,5,20,.9);
    border:1px solid rgba(255,255,255,.09);
    border-radius:14px;
    padding:25px;
}

.group-list h2 {
    font-size:15px;
    color:#e9a1ff;
    margin-bottom:15px;
}

.group-entry {
    padding:17px;
    border:1px solid rgba(255,255,255,.1);
    border-radius:9px;
    margin-bottom:12px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    flex-wrap:wrap;
}

.group-entry strong {
    color:white;
    font-size:14px;
}

.group-entry small {
    display:block;
    color:#9889a6;
    margin-top:6px;
    font-size:11px;
}

.open-group {
    background:#d9baff;
    color:#170d24;
    padding:10px 16px;
    border:0;
    border-radius:6px;
    font-weight:700;
    cursor:pointer;
}

.group-room {
    display:none;
    margin-top:22px;
    padding:25px;
    border-radius:14px;
    background:rgba(9,5,20,.94);
    border:1px solid rgba(200,100,255,.25);
}

.group-room h2 {
    color:#e9a1ff;
    font-size:20px;
    margin-bottom:9px;
}

.group-room p {
    color:#b9abc8;
    font-size:12px;
    line-height:1.8;
}

.room-section {
    margin-top:25px;
    padding-top:20px;
    border-top:1px solid rgba(255,255,255,.1);
}

.room-section h3 {
    color:#e9a1ff;
    font-size:14px;
    margin-bottom:14px;
}

.member-list {
    display:flex;
    flex-wrap:wrap;
    gap:9px;
}

.member {
    padding:10px 14px;
    background:rgba(180,75,255,.12);
    border:1px solid rgba(180,75,255,.2);
    border-radius:7px;
    font-size:11px;
    color:#dfc9ed;
}

.team-file-row {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:10px;
    padding:13px 0;
    border-bottom:1px solid rgba(255,255,255,.08);
    font-size:12px;
    color:#d4c5df;
}

.team-file-row button {
    padding:9px 12px;
    border:0;
    border-radius:5px;
    background:#d9baff;
    cursor:pointer;
    font-weight:700;
    color:#170d24;
}

.back-btn {
    margin-top:20px;
    padding:11px 18px;
    border:1px solid rgba(255,255,255,.2);
    border-radius:7px;
    color:#e4c3f7;
    background:transparent;
    cursor:pointer;
}

@media(max-width:800px) {
    .page {padding:18px 12px;}
    .navbar {padding:10px 12px;gap:12px;align-items:flex-start;flex-direction:column;}
    .brand {font-size:13px;}
    .nav-links {gap:5px;}
    .nav-btn {padding:9px 12px;}
    .container {
        grid-template-columns:1fr;
        gap:30px;
        padding:25px;
    }
    .upload-section {min-height:320px;}
    .team-grid {grid-template-columns:1fr;}
}

</style>
</head>

<body>

<div class="page">

<!-- NAVIGATION -->

<nav class="navbar">

    <div class="brand"><span class="brand-menu" aria-hidden="true">☰</span><span>All Systems</span></div>

    <div class="nav-links">

        <button class="nav-btn active" id="homeNav"
            onclick="showPage('home')">
            HOME
        </button>

        <button class="nav-btn" id="teamNav"
            onclick="showPage('team')">
            TEAM
        </button>

        <button class="nav-btn" id="profileNav"
            onclick="showPage('profile')">
            PROFILE
        </button>

    </div>

</nav>


<!-- ==================================
     HOME
================================== -->

<main id="homePage">

    <div class="container">

        <section class="upload-section" id="dropArea">

            <label class="browse-btn" for="fileInput">
                Select files to send
            </label>

            <input type="file" id="fileInput">

            <p class="drag-text">
                Or drag stuff here
            </p>

            <div class="file-name" id="fileName">
                No file selected
            </div>

            <div class="limit">
                Send files up to 100 MB
            </div>

        </section>


        <section class="info-section">

            <h1>Simple, private file sharing</h1>

            <p class="description">
                Share files with
                <strong>end-to-end encryption</strong>
                and a private link. Your files are
                encrypted in your browser before
                they reach our server.
            </p>

            <button class="primary-btn"
                id="sendBtn" disabled>
                ENCRYPT & SEND ↗
            </button>

            <div class="progress" id="progress">
                <div class="progress-bar" id="progressBar"></div>
            </div>

            <p class="status" id="progressText"></p>

            <div class="result" id="result">

                <h3>✓ ENCRYPTED TRANSFER READY</h3>

                <input class="share-link"
                    id="shareLink" readonly>

                <button class="copy-btn"
                    onclick="copyText('shareLink',this)">
                    COPY PRIVATE LINK
                </button>

            </div>

        </section>

    </div>

    <section class="archive">

        <h2>ACTIVE TRANSFERS</h2>

        {% for item in files %}

        <div class="archive-item">
            <span>🔒 Encrypted transfer · {{ item.id[:12] }}...</span>
            <small>{{ item.date }}</small>
        </div>

        {% else %}

        <div class="archive-item">
            <span>No active transfers</span>
        </div>

        {% endfor %}

    </section>

</main>


<!-- ==================================
     PROFILE PAGE
================================== -->

<main id="profilePage" class="profile-page" style="display:none">
    <section class="profile-card">
        <h1>Profile</h1>
        <p class="profile-description">Your account details and settings</p>
        <div class="profile-menu">
            <div class="profile-menu-item">
                <span class="profile-menu-label">USERNAME</span>
                <strong>{{ username }}</strong>
            </div>
            <button class="profile-menu-item profile-logout" onclick="logout()">
                <span>Log out</span>
                <span aria-hidden="true">›</span>
            </button>
        </div>
    </section>
</main>


<!-- ==================================
     TEAM PAGE
================================== -->

<main id="teamPage" class="team-page">

    <section class="team-heading">

        <h1>Team file sharing</h1>

        <p>
            Create a private group or join an existing team.
            Share files with your group using a private invite code.
            Each group supports up to 20 members.
        </p>

    </section>


    <div class="team-grid">

        <!-- CREATE GROUP -->

        <section class="team-card">

            <h2>Create a group</h2>

            <p>
                Start your own private team.
                Choose a group name and create your own invite code.
            </p>

            <input
                class="field"
                id="createName"
                placeholder="Enter group name"
                maxlength="40"
            >

            <input
                class="field"
                id="createCode"
                type="password"
                placeholder="Create your invite code"
                minlength="12"
                maxlength="128"
                autocomplete="new-password"
            >

            <button class="primary-btn"
                onclick="createGroup()">
                CREATE GROUP +
            </button>

            <div class="team-status" id="createStatus"></div>

        </section>


        <!-- JOIN GROUP -->

        <section class="team-card">

            <h2>Join a group</h2>

            <p>
                Enter the exact group name and invite code
                supplied by your group creator.
            </p>

            <input
                class="field"
                id="joinName"
                placeholder="Enter group name"
                maxlength="40"
            >

            <input
                class="field"
                id="joinCode"
                type="password"
                placeholder="Enter invite code"
                maxlength="128"
                autocomplete="off"
            >

            <button class="primary-btn"
                onclick="joinGroup()">
                JOIN GROUP →
            </button>

            <div class="team-status" id="joinStatus"></div>

        </section>

    </div>


    <!-- MY GROUPS -->

    <section class="group-list">

        <h2>MY GROUPS</h2>

        <div id="groupsList">
            <p class="team-status">Loading your groups...</p>
        </div>

    </section>


    <!-- GROUP ROOM -->

    <section class="group-room" id="groupRoom">

        <h2 id="roomName">Group</h2>

        <p id="roomDescription">
            Private group file sharing
        </p>

        <div class="room-section">

            <h3>GROUP MEMBERS</h3>

            <div class="member-list" id="memberList"></div>

        </div>

        <div class="room-section">

            <h3>SHARE FILE WITH GROUP</h3>

            <input
                class="field"
                type="file"
                id="teamFile"
                style="display:block"
            >

            <button class="primary-btn"
                id="teamUploadBtn"
                onclick="uploadTeamFile()">
                ENCRYPT & SHARE WITH GROUP ↗
            </button>

            <div class="team-status" id="teamUploadStatus"></div>

        </div>

        <div class="room-section">

            <h3>GROUP FILES</h3>

            <div id="teamFiles">
                <p class="team-status">No shared files yet.</p>
            </div>

        </div>

        <button class="back-btn" onclick="closeGroup()">
            ← BACK TO GROUPS
        </button>

    </section>

</main>

</div>


<script>

/* ==========================================
   ACCOUNT
========================================== */

async function logout() {
    try {
        await fetch("/api/auth/logout", {method:"POST", credentials:"same-origin"});
        location.href = "/login";
    } catch {
        alert("Unable to log out. Please try again.");
    }
}


/* ==========================================
   NAVIGATION
========================================== */

function showPage(page) {

    document.getElementById("homePage").style.display =
        page === "home" ? "block" : "none";

    document.getElementById("teamPage").style.display =
        page === "team" ? "block" : "none";

    document.getElementById("profilePage").style.display =
        page === "profile" ? "block" : "none";

    document.getElementById("homeNav").classList.toggle(
        "active", page === "home"
    );

    document.getElementById("teamNav").classList.toggle(
        "active", page === "team"
    );

    document.getElementById("profileNav").classList.toggle(
        "active", page === "profile"
    );

    if (page === "team") loadGroups();

}


/* ==========================================
   HELPERS
========================================== */

async function api(url, options = {}) {

    const response = await fetch(url, {
        credentials: "same-origin",
        ...options,
        headers: {
            ...(options.headers || {})
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.error || "Request failed");
    }

    return data;
}


function encode64(bytes) {

    let binary = "";

    bytes.forEach(b => {
        binary += String.fromCharCode(b);
    });

    return btoa(binary)
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=/g, "");

}


function decode64(value) {

    value = value.replace(/-/g, "+").replace(/_/g, "/");

    value += "=".repeat((4 - value.length % 4) % 4);

    return Uint8Array.from(
        atob(value),
        c => c.charCodeAt(0)
    );

}


async function copyText(id, button) {

    try {

        await navigator.clipboard.writeText(
            document.getElementById(id).value
        );

        button.textContent = "COPIED ✓";

    } catch {

        document.getElementById(id).select();

        document.execCommand("copy");

        button.textContent = "COPIED ✓";

    }

}


/* ==========================================
   PERSONAL FILE TRANSFER
========================================== */

const input = document.getElementById("fileInput");

const drop = document.getElementById("dropArea");

const sendBtn = document.getElementById("sendBtn");

let selectedFile = null;


function chooseFile(file) {

    if (!file) return;

    selectedFile = file;

    document.getElementById("fileName").textContent =
        file.name + " · " +
        (file.size / (1024 * 1024)).toFixed(2) + " MB";

    sendBtn.disabled = false;

    sendBtn.textContent = "ENCRYPT & SEND ↗";

    document.getElementById("result").style.display = "none";

}


input.addEventListener("change", () => {
    chooseFile(input.files[0]);
});


["dragenter", "dragover"].forEach(event => {

    drop.addEventListener(event, e => {

        e.preventDefault();

        drop.classList.add("dragover");

    });

});


["dragleave", "drop"].forEach(event => {

    drop.addEventListener(event, e => {

        e.preventDefault();

        drop.classList.remove("dragover");

    });

});


drop.addEventListener("drop", e => {
    chooseFile(e.dataTransfer.files[0]);
});


sendBtn.addEventListener("click", async () => {

    if (!selectedFile) return;

    if (!crypto.subtle) {
        alert("HTTPS or localhost is required.");
        return;
    }

    if (selectedFile.size > 100 * 1024 * 1024) {
        alert("Maximum file size is 100 MB.");
        return;
    }

    sendBtn.disabled = true;

    sendBtn.textContent = "ENCRYPTING...";

    const progress = document.getElementById("progress");

    const bar = document.getElementById("progressBar");

    const status = document.getElementById("progressText");

    progress.style.display = "block";

    try {

        const rawKey = crypto.getRandomValues(
            new Uint8Array(32)
        );

        const iv = crypto.getRandomValues(
            new Uint8Array(12)
        );

        const key = await crypto.subtle.importKey(
            "raw", rawKey, "AES-GCM", false, ["encrypt"]
        );

        const encrypted = await crypto.subtle.encrypt(
            {name:"AES-GCM", iv},
            key,
            await selectedFile.arrayBuffer()
        );

        status.textContent = "Uploading encrypted file...";

        const xhr = new XMLHttpRequest();

        xhr.open("POST", "/api/upload");

        xhr.setRequestHeader(
            "Content-Type",
            "application/octet-stream"
        );

        xhr.upload.onprogress = e => {

            if (e.lengthComputable) {

                const percent = Math.round(
                    e.loaded / e.total * 100
                );

                bar.style.width = percent + "%";

                status.textContent =
                    "ENCRYPTED UPLOAD: " + percent + "%";

            }

        };

        xhr.onload = () => {

            try {

                const data = JSON.parse(xhr.responseText);

                if (xhr.status !== 200) {
                    throw new Error(data.error || "Upload failed");
                }

                const filename = encode64(
                    new TextEncoder().encode(selectedFile.name)
                );

                const link = location.origin +
                    "/d/" + data.id +
                    "#k=" + encode64(rawKey) +
                    "&iv=" + encode64(iv) +
                    "&name=" + filename;

                document.getElementById("shareLink").value = link;

                document.getElementById("result").style.display = "block";

                bar.style.width = "100%";

                status.textContent = "TRANSFER COMPLETE";

                sendBtn.textContent = "TRANSFER COMPLETE ✓";

            } catch (error) {

                status.textContent = error.message;

                sendBtn.disabled = false;

                sendBtn.textContent = "RETRY TRANSFER ↗";

            }

        };

        xhr.onerror = () => {

            status.textContent = "NETWORK ERROR";

            sendBtn.disabled = false;

            sendBtn.textContent = "RETRY TRANSFER ↗";

        };

        xhr.send(encrypted);

    } catch (error) {

        status.textContent = error.message;

        sendBtn.disabled = false;

        sendBtn.textContent = "RETRY TRANSFER ↗";

    }

});


/* ==========================================
   TEAM GROUP STATE
========================================== */

let currentGroup = null;

let currentGroupCode = null;

let currentGroupSalt = null;

let groupsCache = [];


/* ==========================================
   CREATE GROUP
========================================== */

async function createGroup() {

    const name = document.getElementById("createName").value.trim();

    const code = document.getElementById("createCode").value;

    const status = document.getElementById("createStatus");

    if (!name || !code) {

        status.textContent = "Fill in both group name and invite code.";

        return;

    }

    if (code.length < 12) {

        status.textContent =
            "Use an invite code with at least 12 characters.";

        return;

    }

    status.textContent = "Creating your group...";

    try {

        const data = await api("/api/groups/create", {

            method: "POST",

            headers: {"Content-Type":"application/json"},

            body: JSON.stringify({name, code})

        });

        status.textContent =
            "Group created successfully!";

        document.getElementById("createName").value = "";

        document.getElementById("createCode").value = "";

        loadGroups();

        openGroup(data.id, code);

    } catch (error) {

        status.textContent = error.message;

    }

}


/* ==========================================
   JOIN GROUP
========================================== */

async function joinGroup() {

    const name = document.getElementById("joinName").value.trim();

    const code = document.getElementById("joinCode").value;

    const status = document.getElementById("joinStatus");

    if (!name || !code) {

        status.textContent =
            "Enter the group name and invite code.";

        return;

    }

    status.textContent = "Joining group...";

    try {

        const data = await api("/api/groups/join", {

            method: "POST",

            headers: {"Content-Type":"application/json"},

            body: JSON.stringify({name, code})

        });

        status.textContent = "Successfully joined the group!";

        document.getElementById("joinName").value = "";

        document.getElementById("joinCode").value = "";

        loadGroups();

        openGroup(data.id, code);

    } catch (error) {

        status.textContent = error.message;

    }

}


/* ==========================================
   LOAD MY GROUPS
========================================== */

async function loadGroups() {

    const container = document.getElementById("groupsList");

    try {

        const data = await api("/api/groups");

        groupsCache = data.groups;

        if (!data.groups.length) {

            container.innerHTML =
                '<p class="team-status">You have not joined any groups yet.</p>';

            return;

        }

        container.innerHTML = "";

        data.groups.forEach(group => {

            const entry = document.createElement("div");

            entry.className = "group-entry";

            const info = document.createElement("div");

            const title = document.createElement("strong");

            title.textContent = group.name;

            const detail = document.createElement("small");

            detail.textContent =
                group.members + " / 20 members";

            info.append(title, detail);

            const button = document.createElement("button");

            button.className = "open-group";

            button.textContent = "OPEN GROUP";

            button.onclick = () => {

                const code = prompt(
                    "Enter your group's invite code to open it:"
                );

                if (code) openGroup(group.id, code);

            };

            entry.append(info, button);

            container.appendChild(entry);

        });

    } catch (error) {

        container.textContent = error.message;

    }

}


/* ==========================================
   OPEN GROUP ROOM
========================================== */

async function openGroup(id, code) {

    currentGroup = id;

    currentGroupCode = code;

    try {

        const data = await api(
            "/api/groups/" + id + "?code=" +
            encodeURIComponent(code)
        );

        currentGroupSalt = data.salt;

        document.getElementById("groupRoom").style.display = "block";

        document.getElementById("roomName").textContent = data.name;

        document.getElementById("roomDescription").textContent =
            data.members.length + " / 20 members · Private team space";

        const members = document.getElementById("memberList");

        members.innerHTML = "";

        data.members.forEach((member, index) => {

            const item = document.createElement("div");

            item.className = "member";

            item.textContent = "MEMBER " + (index + 1);

            members.appendChild(item);

        });

        const files = document.getElementById("teamFiles");

        files.innerHTML = "";

        if (!data.files.length) {

            files.textContent = "No shared files yet.";

        } else {

            data.files.forEach(file => {

                const row = document.createElement("div");

                row.className = "team-file-row";

                const label = document.createElement("span");

                label.textContent = file.name;

                const download = document.createElement("button");

                download.textContent = "DECRYPT & DOWNLOAD";

                download.onclick = () => downloadTeamFile(file);

                row.append(label, download);

                files.appendChild(row);

            });

        }

        document.getElementById("groupRoom").scrollIntoView({
            behavior:"smooth"
        });

    } catch (error) {

        alert(error.message);

    }

}


function closeGroup() {

    currentGroup = null;

    currentGroupCode = null;

    currentGroupSalt = null;

    document.getElementById("groupRoom").style.display = "none";

}


/* ==========================================
   GROUP KEY DERIVATION
========================================== */

async function deriveGroupKey(code, salt) {

    const material = await crypto.subtle.importKey(

        "raw",

        new TextEncoder().encode(code),

        "PBKDF2",

        false,

        ["deriveKey"]

    );

    return crypto.subtle.deriveKey(

        {
            name:"PBKDF2",
            salt:decode64(salt),
            iterations:310000,
            hash:"SHA-256"
        },

        material,

        {
            name:"AES-GCM",
            length:256
        },

        false,

        ["encrypt","decrypt"]

    );

}


/* ==========================================
   UPLOAD GROUP FILE
========================================== */

async function uploadTeamFile() {

    const file = document.getElementById("teamFile").files[0];

    const status = document.getElementById("teamUploadStatus");

    const button = document.getElementById("teamUploadBtn");

    if (!currentGroup || !currentGroupCode) {

        status.textContent = "Open a group first.";

        return;

    }

    if (!file) {

        status.textContent = "Select a file first.";

        return;

    }

    if (file.size > 100 * 1024 * 1024) {

        status.textContent = "Maximum file size is 100 MB.";

        return;

    }

    button.disabled = true;

    status.textContent = "Encrypting group file...";

    try {

        const key = await deriveGroupKey(
            currentGroupCode,
            currentGroupSalt
        );

        const iv = crypto.getRandomValues(
            new Uint8Array(12)
        );

        const encrypted = await crypto.subtle.encrypt(

            {name:"AES-GCM",iv},

            key,

            await file.arrayBuffer()

        );

        const filename = encode64(
            new TextEncoder().encode(file.name)
        );

        const response = await fetch(
            "/api/groups/" + currentGroup + "/upload",
            {
                method:"POST",
                headers:{
                    "Content-Type":"application/json",
                    "X-Group-Code":currentGroupCode,
                    "X-File-Name":filename,
                    "X-File-IV":encode64(iv)
                },
                body:encrypted
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Upload failed");
        }

        status.textContent = "File shared successfully!";

        document.getElementById("teamFile").value = "";

        await openGroup(currentGroup, currentGroupCode);

    } catch (error) {

        status.textContent = error.message;

    } finally {

        button.disabled = false;

    }

}


/* ==========================================
   DOWNLOAD GROUP FILE
========================================== */

async function downloadTeamFile(file) {

    try {

        const response = await fetch(
            "/api/groups/" + currentGroup +
            "/file/" + file.id,
            {
                headers:{
                    "X-Group-Code":currentGroupCode
                },
                cache:"no-store"
            }
        );

        if (!response.ok) {
            throw new Error("Unable to retrieve group file.");
        }

        const encrypted = await response.arrayBuffer();

        const key = await deriveGroupKey(
            currentGroupCode,
            currentGroupSalt
        );

        const decrypted = await crypto.subtle.decrypt(

            {
                name:"AES-GCM",
                iv:decode64(file.iv)
            },

            key,

            encrypted

        );

        const blob = new Blob([decrypted]);

        const url = URL.createObjectURL(blob);

        const anchor = document.createElement("a");

        anchor.href = url;

        anchor.download = decodeURIComponent(
            file.name
        );

        document.body.appendChild(anchor);

        anchor.click();

        anchor.remove();

        setTimeout(() => URL.revokeObjectURL(url), 60000);

    } catch (error) {

        alert("Download failed: " + error.message);

    }

}

</script>

</body>
</html>
"""


# ==========================================
# DOWNLOAD PAGE
# ==========================================

DOWNLOAD_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SUPERIOR TRANSFER</title>
<style>
*{box-sizing:border-box}
body{
margin:0;min-height:100vh;display:grid;place-items:center;
padding:20px;background:radial-gradient(circle at 20% 20%,#783d9b,transparent 40%),#100b20;
font-family:Arial,sans-serif;color:white
}
.card{
width:100%;max-width:480px;padding:40px;text-align:center;
background:rgba(8,4,20,.9);border:1px solid rgba(210,130,255,.3);
border-radius:18px;box-shadow:0 20px 70px rgba(0,0,0,.5)
}
h1{color:#ed83ff}
p{color:#b9afc8;line-height:1.7}
button{
width:100%;padding:15px;margin-top:22px;border:0;border-radius:8px;
background:linear-gradient(90deg,#df48ff,#8e5aff);color:white;
font-weight:bold;cursor:pointer
}
#status{margin-top:20px;color:#e49cff;font-size:13px}
</style>
</head>
<body>
<div class="card">
<h1>SUPERIOR TRANSFER</h1>
<p>You have received an encrypted file. Decryption happens locally in your browser.</p>
<button id="downloadBtn">DECRYPT & DOWNLOAD ↓</button>
<div id="status">Waiting for secure decryption...</div>
</div>

<script>
const fileId={{file_id|tojson}};

function decode64(value){
value=value.replace(/-/g,"+").replace(/_/g,"/");
value+="=".repeat((4-value.length%4)%4);
return Uint8Array.from(atob(value),c=>c.charCodeAt(0));
}

document.getElementById("downloadBtn").onclick=async function(){

const button=this;
const status=document.getElementById("status");
button.disabled=true;

try{

const fragment=new URLSearchParams(location.hash.substring(1));

const k=fragment.get("k");
const ivValue=fragment.get("iv");
const nameValue=fragment.get("name");

if(!k||!ivValue||!nameValue)throw Error("Invalid private link.");

status.textContent="Retrieving encrypted file...";

const response=await fetch("/api/file/"+fileId,{cache:"no-store"});

if(!response.ok)throw Error("File expired or unavailable.");

const encrypted=await response.arrayBuffer();

const key=await crypto.subtle.importKey(
"raw",decode64(k),"AES-GCM",false,["decrypt"]
);

status.textContent="Decrypting file...";

const decrypted=await crypto.subtle.decrypt(
{name:"AES-GCM",iv:decode64(ivValue)},key,encrypted
);

const filename=new TextDecoder().decode(decode64(nameValue))
.split(/[\\/]/).pop()||"download";

const url=URL.createObjectURL(new Blob([decrypted]));

const a=document.createElement("a");
a.href=url;
a.download=filename;
document.body.appendChild(a);
a.click();
a.remove();

setTimeout(()=>URL.revokeObjectURL(url),60000);

status.textContent="File decrypted successfully.";
button.textContent="DOWNLOAD COMPLETE ✓";

}catch(error){

status.textContent=error.message;
button.disabled=false;

}

};
</script>
</body>
</html>
"""


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.before_request
def protect_private_api():
    # Authentication endpoints and public shared-file downloads stay public.
    if request.path.startswith("/api/"):
        if request.path in (
            "/api/auth/register",
            "/api/auth/login",
            "/api/auth/logout",
        ):
            return None
        if request.path.startswith("/api/file/"):
            return None
        if not session.get("user_id"):
            return jsonify(error="Please log in to continue."), 401


@app.route("/login", methods=["GET"])
def login_page():
    if session.get("user_id"):
        return redirect("/")
    return render_template_string(AUTH_HTML)


@app.route("/api/auth/register", methods=["POST"])
def register_account():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        return jsonify(error="Username must be 3-30 characters and use only letters, numbers, or underscores."), 400

    if len(email) > 254 or not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", email
    ):
        return jsonify(error="Enter a valid email address."), 400

    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        return jsonify(error="Password must be between 8 and 128 characters."), 400

    if find_account(username):
        return jsonify(error="That username is already registered."), 409
    if find_account(email):
        return jsonify(error="That email address is already registered."), 409

    account_id = uuid.uuid4().hex
    account = {
        "id": account_id,
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    try:
        account_path(account_id).write_text(
            json.dumps(account, indent=2), encoding="utf-8"
        )
    except OSError:
        return jsonify(error="Could not save your account. Check folder permissions."), 500

    session.clear()
    session["user_id"] = account_id
    session["username"] = username
    return jsonify(message="Account created successfully."), 201


@app.route("/api/auth/login", methods=["POST"])
def login_account():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("identifier", "")).strip()
    password = data.get("password", "")

    if not identifier or not isinstance(password, str):
        return jsonify(error="Enter your username/email and password."), 400

    account = find_account(identifier)
    if not account or not check_password_hash(
        account.get("password_hash", ""), password
    ):
        return jsonify(error="Incorrect username/email or password."), 401

    session.clear()
    session["user_id"] = account["id"]
    session["username"] = account["username"]
    return jsonify(message="Logged in successfully.")


@app.route("/api/auth/logout", methods=["POST"])
def logout_account():
    session.clear()
    return jsonify(message="Logged out successfully.")


# ==========================================
# HOME ROUTE
# ==========================================

@app.route("/")
def index():
    if not session.get("user_id"):
        return redirect("/login")

    files = []

    for path in STORAGE.glob("*.json"):

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            if data.get("expires", 0) > time.time():
                files.append({
                    "id": path.stem,
                    "date": datetime.fromtimestamp(
                        data["created"]
                    ).strftime("%d %b %Y")
                })
            else:
                path.unlink(missing_ok=True)
                file_path(path.stem).unlink(missing_ok=True)

        except (OSError, ValueError):
            continue

    return render_template_string(HOME_HTML, files=files, username=session.get("username", "Account"))


# ==========================================
# PERSONAL UPLOAD API
# ==========================================

@app.route("/api/upload", methods=["POST"])
def upload():

    encrypted = request.get_data(cache=False)

    if not encrypted:
        return jsonify(error="Empty file"), 400

    if len(encrypted) > MAX_FILE_SIZE + 16:
        return jsonify(error="File too large"), 413

    file_id = uuid.uuid4().hex

    try:
        file_path(file_id).write_bytes(encrypted)

        metadata = {
            "created": time.time(),
            "expires": time.time() + 86400
        }

        (STORAGE / f"{file_id}.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

    except OSError:
        file_path(file_id).unlink(missing_ok=True)
        return jsonify(error="Storage error"), 500

    return jsonify(id=file_id)


# ==========================================
# PERSONAL DOWNLOAD ROUTE
# ==========================================

@app.route("/d/<file_id>")
def download_page(file_id):

    path = STORAGE / f"{file_id}.json"

    if not valid_id(file_id) or not path.exists():
        abort(404)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["expires"] <= time.time():
            abort(404)
    except (OSError, ValueError, KeyError):
        abort(404)

    return render_template_string(
        DOWNLOAD_HTML,
        file_id=file_id
    )


@app.route("/api/file/<file_id>")
def encrypted_file(file_id):

    if not valid_id(file_id):
        abort(404)

    path = STORAGE / f"{file_id}.json"

    if not path.exists():
        abort(404)

    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if metadata["expires"] <= time.time():
            abort(404)
    except (OSError, ValueError, KeyError):
        abort(404)

    encrypted = file_path(file_id)

    if not encrypted.exists():
        abort(404)

    response = send_file(
        encrypted,
        mimetype="application/octet-stream",
        as_attachment=False
    )

    response.headers["Cache-Control"] = "no-store"

    return response


# ==========================================
# CREATE GROUP API
# ==========================================

@app.route("/api/groups/create", methods=["POST"])
def create_group():

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    code = data.get("code", "")

    if not name or len(name) > 40:
        return jsonify(error="Enter a valid group name."), 400

    if not isinstance(code, str) or len(code) < 12 or len(code) > 128:
        return jsonify(error="Invite code must be 12 to 128 characters."), 400

    group_id = uuid.uuid4().hex

    salt = secrets.token_bytes(16).hex()

    group = {
        "id": group_id,
        "name": name,
        "salt": salt,
        "invite_hash": invite_hash(code, salt),
        "created": time.time(),
        "members": [user_id()],
        "files": []
    }

    save_group(group)

    return jsonify({
        "id": group_id,
        "name": name,
        "members": 1
    })


# ==========================================
# JOIN GROUP API
# ==========================================

@app.route("/api/groups/join", methods=["POST"])
def join_group():

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    code = data.get("code", "")

    if not name or not isinstance(code, str):
        return jsonify(error="Enter group name and invite code."), 400

    if len(code) > 128:
        return jsonify(error="Invalid invite code."), 400

    groups = list(GROUP_STORAGE.glob("*.json"))

    for path in groups:

        group = read_group(path.stem)

        if not group:
            continue

        if group["name"].casefold() != name.casefold():
            continue

        if not hmac.compare_digest(
            group["invite_hash"],
            invite_hash(code, group["salt"])
        ):
            continue

        member = user_id()

        if member not in group["members"]:

            if len(group["members"]) >= MAX_MEMBERS:
                return jsonify(
                    error="This group is full. Maximum 20 members."
                ), 409

            group["members"].append(member)

            save_group(group)

        return jsonify({
            "id": group["id"],
            "name": group["name"],
            "members": len(group["members"])
        })

    return jsonify(
        error="Group not found or invite code is incorrect."
    ), 404


# ==========================================
# LIST MY GROUPS
# ==========================================

@app.route("/api/groups")
def my_groups():

    result = []

    for path in GROUP_STORAGE.glob("*.json"):

        group = read_group(path.stem)

        if group and is_member(group):

            result.append({
                "id": group["id"],
                "name": group["name"],
                "members": len(group["members"])
            })

    return jsonify(groups=result)


# ==========================================
# OPEN GROUP
# ==========================================

@app.route("/api/groups/<group_id>")
def group_details(group_id):

    group = require_member(group_id)

    code = request.args.get("code", "")

    if not isinstance(code, str) or len(code) > 128:
        return jsonify(error="Invalid invite code."), 400

    if not hmac.compare_digest(
        group["invite_hash"],
        invite_hash(code, group["salt"])
    ):
        return jsonify(error="Incorrect invite code."), 403

    return jsonify({
        "id": group["id"],
        "name": group["name"],
        "salt": encode_salt(group["salt"]),
        "members": [
            {"id": member}
            for member in group["members"]
        ],
        "files": group["files"]
    })


def encode_salt(salt):
    import base64
    return base64.urlsafe_b64encode(
        bytes.fromhex(salt)
    ).decode().rstrip("=")


# ==========================================
# GROUP UPLOAD API
# ==========================================

@app.route("/api/groups/<group_id>/upload", methods=["POST"])
def upload_group_file(group_id):

    group = require_member(group_id)

    code = request.headers.get("X-Group-Code", "")

    if not isinstance(code, str) or len(code) > 128:
        return jsonify(error="Invalid invite code."), 400

    if not hmac.compare_digest(
        group["invite_hash"],
        invite_hash(code, group["salt"])
    ):
        return jsonify(error="Incorrect invite code."), 403

    encrypted = request.get_data(cache=False)

    if not encrypted:
        return jsonify(error="Empty file."), 400

    if len(encrypted) > MAX_FILE_SIZE + 16:
        return jsonify(error="File too large."), 413

    iv = request.headers.get("X-File-IV", "")
    name = request.headers.get("X-File-Name", "")

    if not iv or not name or len(iv) > 100 or len(name) > 2000:
        return jsonify(error="Invalid file information."), 400

    file_id = uuid.uuid4().hex

    try:

        team_file_path(file_id).write_bytes(encrypted)

        group["files"].append({
            "id": file_id,
            "name": name,
            "iv": iv,
            "created": time.time()
        })

        save_group(group)

    except OSError:

        team_file_path(file_id).unlink(missing_ok=True)

        return jsonify(error="Storage error."), 500

    return jsonify(id=file_id)


# ==========================================
# GROUP FILE DOWNLOAD API
# ==========================================

@app.route(
    "/api/groups/<group_id>/file/<file_id>"
)
def download_group_file(group_id, file_id):

    group = require_member(group_id)

    code = request.headers.get("X-Group-Code", "")

    if not isinstance(code, str) or len(code) > 128:
        abort(403)

    if not hmac.compare_digest(
        group["invite_hash"],
        invite_hash(code, group["salt"])
    ):
        abort(403)

    if not any(
        f["id"] == file_id
        for f in group["files"]
    ):
        abort(404)

    path = team_file_path(file_id)

    if not path.exists():
        abort(404)

    response = send_file(
        path,
        mimetype="application/octet-stream",
        as_attachment=False
    )

    response.headers["Cache-Control"] = "no-store"

    return response


# ==========================================
# ERROR HANDLING
# ==========================================

@app.errorhandler(413)
def too_large(error):
    return jsonify(error="Maximum file size is 100 MB."), 413


# ==========================================
# START APPLICATION
# ==========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True
    )



