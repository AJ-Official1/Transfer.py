const $ = (id) => document.getElementById(id);
let selectedFile = null;
let encryptedPackage = null;
let selectedDirectory = null;
let activeGroupId = null;
let groups = JSON.parse(localStorage.getItem("st_groups") || "[]");

function bytesToBase64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}
function base64ToBytes(value) {
  const binary = atob(value);
  return Uint8Array.from(binary, c => c.charCodeAt(0));
}
function safeFilename(name) {
  return (name || "file").split(/[\\/]/).pop().replace(/[<>:"|?*\x00-\x1f]/g, "_") || "file";
}
function setStatus(id, message) { $(id).textContent = message; }
function makeBlobUrl(blob) { return URL.createObjectURL(blob); }
function triggerDownload(blob, filename) {
  const url = makeBlobUrl(blob);
  const a = document.createElement("a");
  a.href = url; a.download = safeFilename(filename);
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
function showPage(page) {
  ["home", "team", "profile"].forEach(name => {
    $(`${name}Page`).hidden = name !== page;
    document.querySelector(`[data-page="${name}"]`).classList.toggle("active", name === page);
  });
  if (page === "team") renderGroups();
}
document.querySelectorAll(".nav-btn").forEach(button => button.addEventListener("click", () => showPage(button.dataset.page)));

function chooseFile(file) {
  if (!file) return;
  selectedFile = file;
  encryptedPackage = null;
  $("fileName").textContent = `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB`;
  $("sendBtn").disabled = false;
  $("sendBtn").textContent = "ENCRYPT & PREPARE SHARE ↗";
  $("result").hidden = true;
  setStatus("progressText", "");
}
$("fileInput").addEventListener("change", e => chooseFile(e.target.files[0]));
const drop = $("dropArea");
["dragenter", "dragover"].forEach(type => drop.addEventListener(type, e => {
  e.preventDefault(); drop.classList.add("dragover");
}));
["dragleave", "drop"].forEach(type => drop.addEventListener(type, e => {
  e.preventDefault(); drop.classList.remove("dragover");
}));
drop.addEventListener("drop", e => chooseFile(e.dataTransfer.files[0]));

async function encryptFile(file) {
  if (!crypto.subtle) throw new Error("Web Crypto requires HTTPS or localhost.");
  const rawKey = crypto.getRandomValues(new Uint8Array(32));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await crypto.subtle.importKey("raw", rawKey, "AES-GCM", false, ["encrypt"]);
  const ciphertext = await crypto.subtle.encrypt({name:"AES-GCM", iv}, key, await file.arrayBuffer());
  const keyNote = {
    format: "SUPERIOR-TRANSFER-KEY-1",
    algorithm: "AES-256-GCM",
    key: bytesToBase64(rawKey),
    iv: bytesToBase64(iv),
    filename: safeFilename(file.name),
    mimeType: file.type || "application/octet-stream"
  };
  const packageBlob = new Blob([ciphertext], {type:"application/octet-stream"});
  return {blob:packageBlob, keyNote, filename:safeFilename(file.name), encryptedName:safeFilename(file.name) + ".stx"};
}
$("sendBtn").addEventListener("click", async () => {
  if (!selectedFile) return;
  $("sendBtn").disabled = true;
  $("sendBtn").textContent = "ENCRYPTING...";
  $("progress").style.display = "block";
  $("progressBar").style.width = "20%";
  setStatus("progressText", "Encrypting locally in your browser...");
  try {
    encryptedPackage = await encryptFile(selectedFile);
    $("progressBar").style.width = "100%";
    $("result").hidden = false;
    $("sendBtn").textContent = "ENCRYPTION COMPLETE ✓";
    setStatus("progressText", "Encryption complete. Your file has not been uploaded.");
    addHistory(`Encrypted ${selectedFile.name}`, encryptedPackage);
  } catch (error) {
    setStatus("progressText", error.message);
    $("sendBtn").textContent = "RETRY ENCRYPTION ↗";
    $("sendBtn").disabled = false;
  }
});
function keyNoteBlob() {
  return new Blob([JSON.stringify(encryptedPackage.keyNote, null, 2)], {type:"text/plain"});
}
function openHistoryDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("SuperiorTransferHistory", 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("files")) request.result.createObjectStore("files");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function putHistoryFile(id, pack) {
  if (!pack) return;
  const db = await openHistoryDB();
  await new Promise((resolve, reject) => {
    const tx = db.transaction("files", "readwrite");
    tx.objectStore("files").put({blob:pack.blob, keyNote:pack.keyNote, encryptedName:pack.encryptedName, filename:pack.filename}, id);
    tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
  });
  db.close();
}
async function getHistoryFile(id) {
  const db = await openHistoryDB();
  const result = await new Promise((resolve, reject) => {
    const request = db.transaction("files", "readonly").objectStore("files").get(id);
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
  });
  db.close(); return result;
}
async function deleteHistoryFile(id) {
  const db = await openHistoryDB();
  await new Promise((resolve, reject) => {
    const tx = db.transaction("files", "readwrite"); tx.objectStore("files").delete(id);
    tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
  });
  db.close();
}
async function addHistory(message, pack = null) {
  const entry = {id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random(), message, date:new Date().toLocaleString(), shareable:!!pack};
  if (pack) {
    try { await putHistoryFile(entry.id, pack); }
    catch (error) { console.warn("Could not keep share copy in browser storage:", error); entry.shareable = false; }
  }
  const history = JSON.parse(localStorage.getItem("st_history") || "[]");
  history.unshift(entry);
  const removed = history.splice(12);
  localStorage.setItem("st_history", JSON.stringify(history));
  for (const old of removed) if (old.id) deleteHistoryFile(old.id).catch(()=>{});
  renderHistory();
}
async function shareOrDownloadFiles(encryptedFile, keyFile, encryptedBlob, encryptedName, titleText) {
  const fallback = () => {
    triggerDownload(encryptedBlob, encryptedName);
    triggerDownload(keyFile, keyFile.name);
    alert("Your browser blocked direct file sharing or does not support it here. Both required files have been downloaded. Attach the .stx file and its .key.txt note to your message.");
  };
  if (!navigator.share || !navigator.canShare || !navigator.canShare({files:[encryptedFile,keyFile]})) {
    fallback();
    return "downloaded";
  }
  try {
    await navigator.share({title:"Superior Transfer encrypted file", text:titleText, files:[encryptedFile,keyFile]});
    return "shared";
  } catch (error) {
    // A user cancellation is intentional; permission/security failures use the download fallback.
    if (error && error.name === "AbortError") return "cancelled";
    fallback();
    return "downloaded";
  }
}
let activeShareSource = null;
async function loadSharePackage() {
  if (activeShareSource?.kind === "current") {
    if (!encryptedPackage) throw new Error("Encrypt a file first.");
    return {pack: encryptedPackage, keyBlob: keyNoteBlob()};
  }
  if (activeShareSource?.kind === "history") {
    const saved = await getHistoryFile(activeShareSource.id);
    if (!saved) throw new Error("The saved sharing copy is unavailable. Select the original file and encrypt it again.");
    return {pack: saved, keyBlob: new Blob([JSON.stringify(saved.keyNote, null, 2)], {type:"text/plain"})};
  }
  throw new Error("No file selected for sharing.");
}
function openShareDialog(source, filename) {
  activeShareSource = source;
  $("shareFileName").textContent = filename || "Encrypted file";
  $("shareAppLink").value = location.href.split("#")[0];
  $("shareDialogStatus").textContent = "";
  $("qrPanel").hidden = true;
  $("shareDialog").showModal();
}
async function shareSelectedFile() {
  const {pack, keyBlob} = await loadSharePackage();
  const encryptedFile = new File([pack.blob], pack.encryptedName, {type:"application/octet-stream"});
  const keyFile = new File([keyBlob], pack.filename + ".key.txt", {type:"text/plain"});
  const result = await shareOrDownloadFiles(encryptedFile, keyFile, pack.blob, pack.encryptedName, "Send both attachments. The key note is required to decrypt the file.");
  if (result === "shared" && activeShareSource?.kind === "current") addHistory("Shared encrypted package " + pack.filename, pack);
  if (result === "downloaded" && activeShareSource?.kind === "current") addHistory("Downloaded sharing files for " + pack.filename, pack);
  if (result === "shared") setStatus("shareDialogStatus", "Sharing completed.");
  else if (result === "downloaded") setStatus("shareDialogStatus", "Both files were downloaded. Attach both to your message.");
}
async function renderHistory() {
  const history = JSON.parse(localStorage.getItem("st_history") || "[]");
  const area = $("transferHistory");
  area.innerHTML = "";
  if (!history.length) { area.textContent = "Your recent local activity will appear here."; return; }
  history.forEach(item => {
    const row = document.createElement("div"); row.className = "archive-item";
    const label = document.createElement("span"); label.className = "archive-label"; label.textContent = "🔒 " + item.message;
    const date = document.createElement("small"); date.textContent = item.date;
    const actions = document.createElement("div"); actions.className = "history-actions";
    if (item.shareable && item.id) {
      const share = document.createElement("button"); share.className = "history-action share-history-btn"; share.textContent = "SHARE";
      share.addEventListener("click", () => openShareDialog({kind:"history", id:item.id}, item.message));
      actions.append(share);
    }
    const remove = document.createElement("button"); remove.className = "history-action delete-history-btn"; remove.textContent = "DELETE";
    remove.addEventListener("click", async () => {
      const latest = JSON.parse(localStorage.getItem("st_history") || "[]").filter(entry => entry.id !== item.id);
      localStorage.setItem("st_history", JSON.stringify(latest));
      if (item.id) await deleteHistoryFile(item.id).catch(()=>{});
      renderHistory();
    });
    actions.append(remove);
    const details = document.createElement("div"); details.className = "archive-details"; details.append(label, date);
    row.append(details, actions); area.append(row);
  });
}
$("clearHistoryBtn").addEventListener("click", async () => {
  if (!confirm("Clear all local transfer history? This will remove history records and saved sharing copies from this browser, but it will NOT delete files from your computer folders.")) return;
  const history = JSON.parse(localStorage.getItem("st_history") || "[]");
  localStorage.removeItem("st_history");
  await Promise.all(history.filter(item => item.id).map(item => deleteHistoryFile(item.id).catch(()=>{})));
  renderHistory();
});

$("saveEncryptedBtn").addEventListener("click", () => {
  if (!encryptedPackage) return;
  $("saveDialogStatus").textContent = "";
  $("saveDialog").showModal();
});
async function requestDirectory() {
  if (!window.showDirectoryPicker) throw new Error("Folder selection is not supported in this browser. Use the normal download option.");
  selectedDirectory = await window.showDirectoryPicker({mode:"readwrite"});
  $("directoryStatus").textContent = selectedDirectory.name;
  await saveDirectoryHandle(selectedDirectory);
  return selectedDirectory;
}
async function saveBlobToFolder(folder, blob, filename) {
  const handle = await folder.getFileHandle(safeFilename(filename), {create:true});
  const writable = await handle.createWritable();
  await writable.write(blob);
  await writable.close();
}
async function ensurePermission(handle) {
  if (!handle) return false;
  let permission = await handle.queryPermission({mode:"readwrite"});
  if (permission !== "granted") permission = await handle.requestPermission({mode:"readwrite"});
  return permission === "granted";
}
$("saveToDirectoryBtn").addEventListener("click", async () => {
  try {
    if (!encryptedPackage) return;
    if (!selectedDirectory) await requestDirectory();
    if (!await ensurePermission(selectedDirectory)) throw new Error("Folder permission was not granted.");
    await saveBlobToFolder(selectedDirectory, encryptedPackage.blob, encryptedPackage.encryptedName);
    await saveBlobToFolder(selectedDirectory, keyNoteBlob(), encryptedPackage.filename + ".key.txt");
    setStatus("saveDialogStatus", "Saved encrypted file and key note to " + selectedDirectory.name);
    addHistory("Saved " + encryptedPackage.filename + " to " + selectedDirectory.name, encryptedPackage);
  } catch (error) { setStatus("saveDialogStatus", error.message); }
});
$("createFolderSaveBtn").addEventListener("click", async () => {
  try {
    if (!encryptedPackage) return;
    const root = await requestDirectory();
    const folderName = prompt("Name your new folder:", "Superior Transfer");
    if (!folderName || !folderName.trim()) return;
    const folder = await root.getDirectoryHandle(folderName.trim().replace(/[<>:"/\\|?*]/g, "_"), {create:true});
    await saveBlobToFolder(folder, encryptedPackage.blob, encryptedPackage.encryptedName);
    await saveBlobToFolder(folder, keyNoteBlob(), encryptedPackage.filename + ".key.txt");
    setStatus("saveDialogStatus", "Created folder and saved both files.");
    addHistory("Created folder " + folder.name + " and saved " + encryptedPackage.filename, encryptedPackage);
  } catch (error) { setStatus("saveDialogStatus", error.message); }
});
$("browserDownloadBtn").addEventListener("click", () => {
  if (!encryptedPackage) return;
  triggerDownload(encryptedPackage.blob, encryptedPackage.encryptedName);
  triggerDownload(keyNoteBlob(), encryptedPackage.filename + ".key.txt");
  setStatus("saveDialogStatus", "Browser downloads started for the encrypted file and key note.");
  addHistory("Downloaded encrypted package " + encryptedPackage.filename, encryptedPackage);
});
$("shareEncryptedBtn").addEventListener("click", () => {
  if (encryptedPackage) openShareDialog({kind:"current"}, encryptedPackage.filename);
});
$("closeShareDialog").addEventListener("click", () => $("shareDialog").close());
$("copyShareLinkBtn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("shareAppLink").value);
    setStatus("shareDialogStatus", "Website link copied. Remember: this link does not include the file.");
  } catch {
    $("shareAppLink").select();
    setStatus("shareDialogStatus", "Copy is blocked by this browser. Select the link and copy it manually.");
  }
});
$("nativeShareBtn").addEventListener("click", async () => {
  try { await shareSelectedFile(); }
  catch (error) { if (error.name !== "AbortError") setStatus("shareDialogStatus", "Could not share file: " + error.message); }
});
$("showQrBtn").addEventListener("click", () => {
  const url = location.href.split("#")[0];
  $("shareQrImage").src = "https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=8&data=" + encodeURIComponent(url);
  $("qrPanel").hidden = false;
  setStatus("shareDialogStatus", "This QR code opens the website only; it is not a download link for your file.");
});
$("decryptBtn").addEventListener("click", async () => {
  const file = $("encryptedInput").files[0];
  try {
    if (!file) throw new Error("Choose the encrypted .stx file first.");
    const note = JSON.parse($("keyInput").value);
    if (note.format !== "SUPERIOR-TRANSFER-KEY-1") throw new Error("This key note is not recognized.");
    const rawKey = base64ToBytes(note.key), iv = base64ToBytes(note.iv);
    const key = await crypto.subtle.importKey("raw", rawKey, "AES-GCM", false, ["decrypt"]);
    const decrypted = await crypto.subtle.decrypt({name:"AES-GCM", iv}, key, await file.arrayBuffer());
    triggerDownload(new Blob([decrypted], {type:note.mimeType || "application/octet-stream"}), note.filename || "decrypted-file");
    setStatus("receiveStatus", "Decryption successful. Your browser download has started.");
    addHistory("Decrypted " + (note.filename || file.name));
  } catch (error) { setStatus("receiveStatus", "Unable to decrypt: " + error.message); }
});

/* Persist the chosen folder handle in IndexedDB when the browser supports it. */
function openHandleDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("SuperiorTransferSettings", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("settings");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function saveDirectoryHandle(handle) {
  try {
    const db = await openHandleDB();
    await new Promise((resolve, reject) => {
      const tx = db.transaction("settings", "readwrite");
      tx.objectStore("settings").put(handle, "saveDirectory");
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch { /* Directory remains selected for this page session. */ }
}
async function restoreDirectoryHandle() {
  try {
    const db = await openHandleDB();
    const handle = await new Promise((resolve, reject) => {
      const request = db.transaction("settings").objectStore("settings").get("saveDirectory");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    db.close();
    if (handle) {
      selectedDirectory = handle;
      $("directoryStatus").textContent = handle.name + " (saved in this browser)";
    }
  } catch {}
}
$("chooseDirectoryBtn").addEventListener("click", async () => {
  try { await requestDirectory(); }
  catch (error) { alert(error.message); }
});
$("clearDirectoryBtn").addEventListener("click", async () => {
  selectedDirectory = null;
  $("directoryStatus").textContent = "No folder selected";
  try {
    const db = await openHandleDB();
    await new Promise(resolve => {
      const tx = db.transaction("settings", "readwrite");
      tx.objectStore("settings").delete("saveDirectory");
      tx.oncomplete = resolve;
    });
    db.close();
  } catch {}
});
$("displayName").value = localStorage.getItem("st_displayName") || "";
$("displayName").addEventListener("input", e => localStorage.setItem("st_displayName", e.target.value));

/* Browser-local groups: these do not synchronize with other devices or users. */
function saveGroups() { localStorage.setItem("st_groups", JSON.stringify(groups)); }
function renderGroups() {
  const list = $("groupsList"); list.innerHTML = "";
  if (!groups.length) { list.textContent = "No local groups yet."; return; }
  groups.forEach(group => {
    const row = document.createElement("div"); row.className = "group-entry";
    const info = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = group.name;
    const meta = document.createElement("p"); meta.className = "muted"; meta.textContent = `${group.files.length} locally prepared file(s)`;
    info.append(title, meta);
    const open = document.createElement("button"); open.className = "open-group"; open.textContent = "OPEN GROUP";
    open.addEventListener("click", () => openGroup(group.id));
    row.append(info, open); list.append(row);
  });
}
$("createGroupBtn").addEventListener("click", () => {
  const name = $("createName").value.trim();
  if (!name) return setStatus("createStatus", "Enter a group name.");
  const code = crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  const group = {id:crypto.randomUUID(), name, code, files:[]};
  groups.push(group); saveGroups(); renderGroups();
  $("createName").value = "";
  setStatus("createStatus", `Group created in this browser. Local invite code: ${code}`);
});
$("joinGroupBtn").addEventListener("click", () => {
  const name = $("joinName").value.trim().toLowerCase(), code = $("joinCode").value;
  const group = groups.find(g => g.name.toLowerCase() === name && g.code === code);
  if (!group) return setStatus("joinStatus", "No matching local group and invite code were found.");
  openGroup(group.id);
});
function openGroup(id) {
  const group = groups.find(g => g.id === id); if (!group) return;
  activeGroupId = id; $("roomName").textContent = group.name; $("groupRoom").hidden = false;
  renderTeamFiles(group); $("groupRoom").scrollIntoView({behavior:"smooth",block:"start"});
}
function renderTeamFiles(group) {
  const area = $("teamFiles"); area.innerHTML = "";
  if (!group.files.length) { area.textContent = "No files prepared yet."; return; }
  group.files.forEach(file => {
    const row = document.createElement("div"); row.className = "team-file-row";
    const name = document.createElement("span"); name.textContent = file.name;
    const save = document.createElement("button"); save.className = "open-group"; save.textContent = "DOWNLOAD ENCRYPTED";
    save.addEventListener("click", () => triggerDownload(new Blob([Uint8Array.from(atob(file.data), c=>c.charCodeAt(0))]), file.name + ".stx"));
    row.append(name, save); area.append(row);
  });
}
$("teamPrepareBtn").addEventListener("click", async () => {
  const file = $("teamFile").files[0], group = groups.find(g => g.id === activeGroupId);
  try {
    if (!group) throw new Error("Open a local group first.");
    if (!file) throw new Error("Choose a file first.");
    const pack = await encryptFile(file);
    const data = bytesToBase64(new Uint8Array(await pack.blob.arrayBuffer()));
    group.files.push({name:pack.filename, data, keyNote:pack.keyNote});
    saveGroups(); renderTeamFiles(group);
    setStatus("teamUploadStatus", "Encrypted file stored in this browser's local group. Export and share the key note separately to allow decryption.");
    addHistory("Prepared team file " + pack.filename);
    triggerDownload(new Blob([JSON.stringify(pack.keyNote,null,2)],{type:"text/plain"}), pack.filename + ".key.txt");
  } catch (error) { setStatus("teamUploadStatus", error.message); }
});
$("closeGroupBtn").addEventListener("click", () => { activeGroupId = null; $("groupRoom").hidden = true; });

$("saveDialog").addEventListener("click", e => {
  if (e.target === $("saveDialog")) $("saveDialog").close();
});
renderHistory();
renderGroups();
restoreDirectoryHandle();
