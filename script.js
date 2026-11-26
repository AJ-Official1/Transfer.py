
let directoryHandle = null;
let selectedFiles = [];

const folderStatus = document.getElementById("folderStatus");
const fileInput = document.getElementById("fileInput");
const fileList = document.getElementById("fileList");

const createFolderBtn = document.getElementById("createFolderBtn");
const saveFilesBtn = document.getElementById("saveFilesBtn");
const downloadBtn = document.getElementById("downloadBtn");

// Select or create a folder
createFolderBtn.addEventListener("click", async () => {
    if (!window.showDirectoryPicker) {
        alert("Your browser does not support folder access. Try a recent version of Chrome or Edge.");
        return;
    }

    try {
        directoryHandle = await window.showDirectoryPicker({
            mode: "readwrite"
        });

        folderStatus.textContent =
            "Connected folder: " + directoryHandle.name;

        alert("Save folder selected successfully!");
    } catch (error) {
        if (error.name !== "AbortError") {
            alert("Could not select folder.");
        }
    }
});

// Select files
fileInput.addEventListener("change", () => {
    selectedFiles = Array.from(fileInput.files);

    fileList.innerHTML = "";

    if (selectedFiles.length === 0) {
        fileList.innerHTML = "<li>No files selected</li>";
        return;
    }

    selectedFiles.forEach(file => {
        const li = document.createElement("li");
        li.textContent = file.name;
        fileList.appendChild(li);
    });
});

// Save files into selected folder
saveFilesBtn.addEventListener("click", async () => {
    if (!directoryHandle) {
        alert("Please select a save folder first.");
        return;
    }

    if (selectedFiles.length === 0) {
        alert("Please select files first.");
        return;
    }

    try {
        const permission = await directoryHandle.requestPermission({
            mode: "readwrite"
        });

        if (permission !== "granted") {
            alert("Folder permission was not granted.");
            return;
        }

        for (const file of selectedFiles) {
            const fileHandle = await directoryHandle.getFileHandle(
                file.name,
                { create: true }
            );

            const writable = await fileHandle.createWritable();
            await writable.write(file);
            await writable.close();
        }

        alert("Files saved successfully!");
    } catch (error) {
        console.error(error);
        alert("Could not save files.");
    }
});

// Download selected files individually
downloadBtn.addEventListener("click", () => {
    if (selectedFiles.length === 0) {
        alert("Please select files first.");
        return;
    }

    selectedFiles.forEach(file => {
        const url = URL.createObjectURL(file);
        const link = document.createElement("a");

        link.href = url;
        link.download = file.name;
        link.click();

        URL.revokeObjectURL(url);
    });
});
