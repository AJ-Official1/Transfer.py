const $ = (id) => document.getElementById(id);
let selectedFile = null;
let currentFile = null;
let selectedDirectory = null;
let activeGroupId = null;
let groups = JSON.parse(localStorage.getItem("st_groups") || "[]");
let activeShareSource = null;

function safeFilename(name) {
  return (name || "file").split(/[\\/]/).pop().replace(/[<>:"|?*\x00-\x1f]/g, "_") || "file";
}
function setStatus(id, message) { const node = $(id); if (node) node.textContent = message; }
function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
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
  currentFile = null;
  $("fileName").textContent = `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB`;
  $("sendBtn").disabled = false;
  $("sendBtn").textContent = "PREPARE FILE ↗";
  $("result").hidden = true;
  setStatus("progressText", "");
}
$("fileInput").addEventListener("change", e => chooseFile(e.target.files[0]));
const drop = $("dropArea");
["dragenter", "dragover"].forEach(type => drop.addEventListener(type, e => { e.preventDefault(); drop.classList.add("dragover"); }));
["dragleave", "drop"].forEach(type => drop.addEventListener(type, e => { e.preventDefault(); drop.classList.remove("dragover"); }));
drop.addEventListener("drop", e => chooseFile(e.dataTransfer.files[0]));

function openHistoryDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("SuperiorTransferHistory", 2);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("files")) request.result.createObjectStore("files");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function putHistoryFile(id, file) {
  const db = await openHistoryDB();
  try {
    await new Promise((resolve, reject) => {
      const tx = db.transaction("files", "readwrite");
      tx.objectStore("files").put({blob:file, filename:file.name, type:file.type || "application/octet-stream"}, id);
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
    });
  } finally { db.close(); }
}
async function getHistoryFile(id) {
  const db = await openHistoryDB();
  try {
    return await new Promise((resolve, reject) => {
      const req = db.transaction("files", "readonly").objectStore("files").get(id);
      req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
    });
  } finally { db.close(); }
}
async function deleteHistoryFile(id) {
  const db = await openHistoryDB();
  try {
    await new Promise((resolve, reject) => {
      const tx = db.transaction("files", "readwrite"); tx.objectStore("files").delete(id);
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
    });
  } finally { db.close(); }
}
async function addHistory(message, file) {
  const entry = {id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`, message, date:new Date().toLocaleString(), plainFile:!!file};
  if (file) {
    try { await putHistoryFile(entry.id, file); }
    catch (error) { console.warn("Could not save a local history copy:", error); entry.plainFile = false; }
  }
  const history = JSON.parse(localStorage.getItem("st_history") || "[]");
  history.unshift(entry);
  const removed = history.splice(12);
  localStorage.setItem("st_history", JSON.stringify(history));
  for (const old of removed) if (old.id) deleteHistoryFile(old.id).catch(() => {});
  renderHistory();
}

$("sendBtn").addEventListener("click", async () => {
  if (!selectedFile) return;
  const button = $("sendBtn");
  button.disabled = true; button.textContent = "PREPARING...";
  $("progress").style.display = "block"; $("progressBar").style.width = "100%";
  setStatus("progressText", "Your original file is ready. It is not encrypted or uploaded to a server.");
  currentFile = selectedFile;
  $("result").hidden = false;
  button.textContent = "FILE READY ✓";
  await addHistory(`Prepared ${selectedFile.name}`, selectedFile);
});

async function resolveShareFile() {
  if (activeShareSource?.kind === "current") {
    if (!currentFile) throw new Error("Choose a file first.");
    return currentFile;
  }
  if (activeShareSource?.kind === "history") {
    const saved = await getHistoryFile(activeShareSource.id);
    if (!saved?.blob) throw new Error("This file is no longer available in local browser storage.");
    return new File([saved.blob], saved.filename || activeShareSource.filename || "shared-file", {type:saved.type || saved.blob.type});
  }
  throw new Error("No file selected.");
}
function getWebsiteShareUrl() {
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  return url.href;
}
async function openShareDialog(source, filename) {
  activeShareSource = source;
  $("shareFileName").textContent = filename || "File ready";
  const websiteUrl = getWebsiteShareUrl();
  $("shareLinkInput").value = websiteUrl;
  $("qrPanel").hidden = true;
  $("shareQrImage").removeAttribute("src");
  $("shareDialogStatus").textContent = "The link opens this website. To send the actual file, use Share to send it as an attachment.";
  $("shareDialog").showModal();
}
async function shareSelectedFile() {
  const file = await resolveShareFile();
  if (navigator.share && navigator.canShare && navigator.canShare({files:[file]})) {
    try {
      await navigator.share({title:"Superior Transfer file", text:"File shared with you.", files:[file]});
      setStatus("shareDialogStatus", "The sharing menu was opened.");
      return;
    } catch (error) {
      if (error?.name === "AbortError") {
        setStatus("shareDialogStatus", "Sharing was cancelled.");
        return;
      }
      console.warn("Native file sharing failed:", error);
    }
  }
  triggerDownload(file, file.name);
  setStatus("shareDialogStatus", "Your browser cannot share files directly here. The file has been downloaded; attach it to WhatsApp, email, or another app.");
}

async function renderHistory() {
  const history = JSON.parse(localStorage.getItem("st_history") || "[]");
  const area = $("transferHistory"); area.innerHTML = "";
  if (!history.length) { area.textContent = "Your recent local activity will appear here."; return; }
  history.forEach(item => {
    const row = document.createElement("div"); row.className = "archive-item";
    const label = document.createElement("span"); label.className = "archive-label";
    label.textContent = (item.plainFile ? "📄 " : "ℹ️ ") + item.message;
    const date = document.createElement("small"); date.textContent = item.date;
    const actions = document.createElement("div"); actions.className = "history-actions";
    if (item.plainFile && item.id) {
      const share = document.createElement("button"); share.className = "history-action share-history-btn"; share.textContent = "SHARE";
      share.addEventListener("click", () => openShareDialog({kind:"history", id:item.id}, item.message));
      actions.append(share);
    }
    const remove = document.createElement("button"); remove.className = "history-action delete-history-btn"; remove.textContent = "DELETE";
    remove.addEventListener("click", async () => {
      const latest = JSON.parse(localStorage.getItem("st_history") || "[]").filter(entry => entry.id !== item.id);
      localStorage.setItem("st_history", JSON.stringify(latest));
      if (item.id) await deleteHistoryFile(item.id).catch(() => {});
      renderHistory();
    });
    actions.append(remove);
    const details = document.createElement("div"); details.className = "archive-details"; details.append(label, date);
    row.append(details, actions); area.append(row);
  });
}
$("clearHistoryBtn").addEventListener("click", async () => {
  if (!confirm("Clear all local transfer history and its browser-stored copies? Files already saved in your computer folders will not be deleted.")) return;
  const history = JSON.parse(localStorage.getItem("st_history") || "[]");
  localStorage.removeItem("st_history");
  await Promise.all(history.filter(item => item.id).map(item => deleteHistoryFile(item.id).catch(() => {})));
  renderHistory();
});

$("saveFileBtn").addEventListener("click", () => {
  if (!currentFile) return;
  $("saveDialogStatus").textContent = "";
  $("saveDialog").showModal();
});
function directoryPickerAvailable() { return window.isSecureContext && typeof window.showDirectoryPicker === "function"; }
async function requestDirectory() {
  if (!window.isSecureContext) throw new Error("Folder saving requires HTTPS. Open your GitHub Pages address.");
  if (typeof window.showDirectoryPicker !== "function") throw new Error("This browser does not support folder selection. Use the normal browser download option, or try Chrome or Edge.");
  selectedDirectory = await window.showDirectoryPicker({mode:"readwrite"});
  $("directoryStatus").textContent = selectedDirectory.name + " (selected)";
  await saveDirectoryHandle(selectedDirectory);
  return selectedDirectory;
}
async function saveBlobToFolder(folder, blob, filename) {
  const handle = await folder.getFileHandle(safeFilename(filename), {create:true});
  const writable = await handle.createWritable();
  await writable.write(blob); await writable.close();
}
async function ensurePermission(handle) {
  if (!handle) return false;
  let permission = await handle.queryPermission({mode:"readwrite"});
  if (permission !== "granted") permission = await handle.requestPermission({mode:"readwrite"});
  return permission === "granted";
}
$("saveToDirectoryBtn").addEventListener("click", async () => {
  try {
    if (!currentFile) return;
    if (!selectedDirectory) await requestDirectory();
    if (!await ensurePermission(selectedDirectory)) throw new Error("Folder permission was not granted.");
    await saveBlobToFolder(selectedDirectory, currentFile, currentFile.name);
    setStatus("saveDialogStatus", `Saved ${currentFile.name} to ${selectedDirectory.name}.`);
    await addHistory(`Saved ${currentFile.name} to ${selectedDirectory.name}`, currentFile);
  } catch (error) { setStatus("saveDialogStatus", error.message); }
});
$("createFolderSaveBtn").addEventListener("click", async () => {
  try {
    if (!currentFile) return;
    const root = selectedDirectory || await requestDirectory();
    if (!await ensurePermission(root)) throw new Error("Folder access was not granted. Choose the folder again.");
    const folderName = prompt("Name your new folder:", "Superior Transfer");
    if (!folderName?.trim()) return;
    const folder = await root.getDirectoryHandle(folderName.trim().replace(/[<>:"/\\|?*]/g, "_"), {create:true});
    await saveBlobToFolder(folder, currentFile, currentFile.name);
    setStatus("saveDialogStatus", `Created ${folder.name} and saved ${currentFile.name}.`);
    await addHistory(`Saved ${currentFile.name} in folder ${folder.name}`, currentFile);
  } catch (error) { setStatus("saveDialogStatus", error.message); }
});
$("browserDownloadBtn").addEventListener("click", async () => {
  if (!currentFile) return;
  triggerDownload(currentFile, currentFile.name);
  setStatus("saveDialogStatus", "Your original file download has started.");
  await addHistory(`Downloaded ${currentFile.name}`, currentFile);
});
$("shareFileBtn").addEventListener("click", () => {
  if (currentFile) openShareDialog({kind:"current"}, currentFile.name);
});
$("closeShareDialog").addEventListener("click", () => $("shareDialog").close());
$("copyShareLinkBtn").addEventListener("click", async () => {
  const link = $("shareLinkInput").value || getWebsiteShareUrl();
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(link);
    } else {
      const input = $("shareLinkInput");
      input.focus(); input.select();
      const copied = document.execCommand("copy");
      input.setSelectionRange(0, 0);
      if (!copied) throw new Error("Copy is unavailable. Select and copy the website address manually.");
    }
    setStatus("shareDialogStatus", "Website link copied. Remember to send the file separately using Share.");
  } catch (error) { setStatus("shareDialogStatus", error.message || "Could not copy the link. Select the address and copy it manually."); }
});
$("showQrBtn").addEventListener("click", () => {
  const panel = $("qrPanel");
  if (!panel.hidden) { panel.hidden = true; return; }
  const link = getWebsiteShareUrl();
  // The QR contains only the public website address, never the file itself.
  $("shareQrImage").src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=8&data=${encodeURIComponent(link)}`;
  panel.hidden = false;
  setStatus("shareDialogStatus", "This QR code opens the website only. Send the file separately as an attachment.");
});
$("nativeShareBtn").addEventListener("click", async () => {
  try { await shareSelectedFile(); }
  catch (error) { setStatus("shareDialogStatus", error.message); }
});


/* Save-directory selection and persistence */
function openHandleDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("SuperiorTransferSettings", 1);
    request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains("settings")) request.result.createObjectStore("settings"); };
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
  });
}
async function saveDirectoryHandle(handle) {
  const db = await openHandleDB();
  try {
    await new Promise((resolve, reject) => {
      const tx = db.transaction("settings", "readwrite"); tx.objectStore("settings").put(handle, "saveDirectory");
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error || new Error("Could not remember the folder."));
    });
  } finally { db.close(); }
}
async function restoreDirectoryHandle() {
  if (!directoryPickerAvailable()) {
    $("directoryStatus").textContent = "Folder selection unavailable in this browser";
    $("chooseDirectoryBtn").disabled = true;
    $("directoryHelp").textContent = !window.isSecureContext ? "Open this site using its HTTPS GitHub Pages address." : "Try the latest Chrome or Edge, or use normal browser downloads.";
    return;
  }
  try {
    const db = await openHandleDB();
    const handle = await new Promise((resolve, reject) => {
      const req = db.transaction("settings", "readonly").objectStore("settings").get("saveDirectory");
      req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
    });
    db.close();
    if (handle) {
      selectedDirectory = handle;
      const permission = await handle.queryPermission({mode:"readwrite"});
      $("directoryStatus").textContent = handle.name + (permission === "granted" ? " (ready)" : " (permission needed when saving)");
      $("directoryHelp").textContent = permission === "granted" ? "Folder remembered in this browser." : "Folder remembered. Your browser may ask you to allow access again when saving.";
    }
  } catch (error) { console.warn("Could not restore save folder:", error); $("directoryHelp").textContent = "Your browser could not restore the saved folder. Choose it again."; }
}
$("chooseDirectoryBtn").addEventListener("click", async () => {
  try { await requestDirectory(); $("directoryHelp").textContent = "Folder selected and remembered in this browser."; }
  catch (error) { if (error.name !== "AbortError") $("directoryHelp").textContent = error.message; }
});
$("clearDirectoryBtn").addEventListener("click", async () => {
  selectedDirectory = null; $("directoryStatus").textContent = "No folder selected"; $("directoryHelp").textContent = "Choose a folder to use it as your save location.";
  try {
    const db = await openHandleDB();
    await new Promise((resolve, reject) => { const tx = db.transaction("settings", "readwrite"); tx.objectStore("settings").delete("saveDirectory"); tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); });
    db.close();
  } catch (error) { console.warn("Could not forget saved folder:", error); }
});
$("displayName").value = localStorage.getItem("st_displayName") || "";
$("displayName").addEventListener("input", e => localStorage.setItem("st_displayName", e.target.value));

/* Local-only groups: group data does not sync across devices or browsers. */
function saveGroups() { localStorage.setItem("st_groups", JSON.stringify(groups)); }
function renderGroups() {
  const list = $("groupsList"); list.innerHTML = "";
  if (!groups.length) { list.textContent = "No local groups yet."; return; }
  groups.forEach(group => {
    const row = document.createElement("div"); row.className = "group-entry";
    const info = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = group.name;
    const meta = document.createElement("p"); meta.className = "muted"; meta.textContent = `${group.files.length} file(s) stored locally`;
    info.append(title, meta);
    const open = document.createElement("button"); open.className = "open-group"; open.textContent = "OPEN GROUP"; open.addEventListener("click", () => openGroup(group.id));
    row.append(info, open); list.append(row);
  });
}
$("createGroupBtn").addEventListener("click", () => {
  const name = $("createName").value.trim(); if (!name) return setStatus("createStatus", "Enter a group name.");
  const code = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}${Math.random()}`).replace(/-/g, "").slice(0, 16);
  groups.push({id:crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), name, code, files:[]}); saveGroups(); renderGroups(); $("createName").value = "";
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
  activeGroupId = id; $("roomName").textContent = group.name; $("groupRoom").hidden = false; renderTeamFiles(group);
  $("groupRoom").scrollIntoView({behavior:"smooth", block:"start"});
}
function renderTeamFiles(group) {
  const area = $("teamFiles"); area.innerHTML = "";
  if (!group.files.length) { area.textContent = "No files added yet."; return; }
  group.files.forEach((file, index) => {
    const row = document.createElement("div"); row.className = "team-file-row";
    const name = document.createElement("span"); name.textContent = file.name;
    const save = document.createElement("button"); save.className = "open-group"; save.textContent = "DOWNLOAD FILE";
    save.addEventListener("click", () => triggerDownload(new Blob([Uint8Array.from(atob(file.data), c => c.charCodeAt(0))], {type:file.type || "application/octet-stream"}), file.name));
    row.append(name, save); area.append(row);
  });
}
$("teamPrepareBtn").addEventListener("click", async () => {
  const file = $("teamFile").files[0], group = groups.find(g => g.id === activeGroupId);
  try {
    if (!group) throw new Error("Open a local group first.");
    if (!file) throw new Error("Choose a file first.");
    const data = btoa(Array.from(new Uint8Array(await file.arrayBuffer()), byte => String.fromCharCode(byte)).join(""));
    group.files.push({name:file.name, type:file.type, data}); saveGroups(); renderTeamFiles(group);
    setStatus("teamUploadStatus", "Original file saved in this browser's local group. It is not encrypted or uploaded online.");
    await addHistory(`Added ${file.name} to local group ${group.name}`, file);
  } catch (error) { setStatus("teamUploadStatus", error.message); }
});
$("closeGroupBtn").addEventListener("click", () => { activeGroupId = null; $("groupRoom").hidden = true; });
$("saveDialog").addEventListener("click", e => { if (e.target === $("saveDialog")) $("saveDialog").close(); });

renderHistory();
renderGroups();
restoreDirectoryHandle();
