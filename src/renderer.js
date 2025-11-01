const { ipcRenderer } = require("electron");

window.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("url");
  const destInput = document.getElementById("dest");
  const selectButton = document.getElementById("select-dest");
  const startButton = document.getElementById("start");
  const stopButton = document.getElementById("stop");
  const clearButton = document.getElementById("clear");
  const vmcButton = document.getElementById("vmc");
  const log = document.getElementById("log");
  const logContainer = document.getElementById("log-container");
  const progressFill = document.querySelector(".progress-fill");
  const progressText = document.getElementById("progress-text");

  let downloadInProgress = false; // Track if download is in progress
  let currentDestPath = null;
  let currentVhdFilename = null;

  // Select destination folder
  selectButton.addEventListener("click", async () => {
    const folder = await ipcRenderer.invoke("select-dest");
    if (folder && destInput) destInput.value = folder;
  });

  // Start download
  startButton.addEventListener("click", () => {
    console.log("Start button clicked"); // Log for debugging
    log.textContent = "";
    // Add custom text content before starting download
    // Add the separator and new content
    log.textContent += `
******************************************
* VHD to USB Downloader             *
* Your download is about to start...  *
******************************************
`;

    if (!urlInput.value || !destInput.value) {
      alert("Please enter a URL and select a destination!");
      return;
    }

    log.textContent += "\nStarting download..."; // Appending to existing log

    // Reset progress bar
    progressFill.style.width = "0%";
    progressText.textContent = "0%";

    // Assign paths to variables in a higher scope
    currentVhdFilename = urlInput.value.split("/").pop();
    currentDestPath = destInput.value;

    const fullDestPath = `${currentDestPath}/${currentVhdFilename}`;
    ipcRenderer.send("start-download", urlInput.value, fullDestPath);

    // Mark download as in progress
    downloadInProgress = true;
    stopButton.disabled = false; // Enable stop button after starting
    startButton.disabled = true; // Disable start button after starting
  });

  // Stop download
  stopButton.addEventListener("click", () => {
    if (downloadInProgress) {
      ipcRenderer.send("stop-download"); // Send message to stop the download
      log.textContent += "\nDownload stopped by user.\n";
      progressFill.style.width = "0%";
      progressText.textContent = "0%";
      stopButton.disabled = true; // Disable stop button after stopping
      startButton.disabled = false; // Enable start button after stopping
      downloadInProgress = false; // Reset the download state
    }
  });

  // Clear console
  clearButton.addEventListener("click", () => {
    console.log("clear button clicked"); // Log for debugging
    log.textContent = "";
    // Add custom text content before starting download
    // Add the separator and new content
    log.textContent += `
******************************************
* VHD to USB Downloader             *
******************************************
`;
  });

  // VMC button click listener
  vmcButton.addEventListener("click", () => {
    const destPath = destInput.value;
    if (!destPath) {
      alert("Please select a destination folder first!");
      return;
    }

    const vhdFilename = urlInput.value.split("/").pop();
    ipcRenderer.send("create-vmc-file", destPath, vhdFilename);
  });

  // Receive logs from the main process
  ipcRenderer.on("download-log", (event, msg) => {
    log.textContent += msg + "\n";

    // Update progress bar if the log contains a percentage
    const match = msg.match(/(\d+(\.\d+)?)%/);
    if (match) {
      const percent = parseFloat(match[1]);
      progressFill.style.width = `${percent}%`;
      progressText.textContent = `${percent}%`;
    }
    const maxLines = 500;
    // Trim old messages if the log gets too long
    const lines = log.textContent.split("\n");
    if (lines.length > maxLines) {
      log.textContent = lines.slice(lines.length - maxLines).join("\n");
    }
    // Automatically scroll to the bottom
    logContainer.scrollTop = logContainer.scrollHeight;
  });

  // When the download is done, send data to the main process
  ipcRenderer.on("download-done", (event, code) => {
    log.textContent += `\nDownload finished with exit code ${code}\n`;
    progressFill.style.width = "100%";
    progressText.textContent = "100%";
    stopButton.disabled = true;
    downloadInProgress = false;

    // Send a single message with all necessary data
    // The main process will handle all post-download logic from here
    ipcRenderer.send(
      "download-finished",
      code,
      currentDestPath,
      currentVhdFilename
    );
  });

  // Clear log button
  const clearLogBtn = document.querySelector(".clear-log");
  clearLogBtn?.addEventListener("click", () => {
    log.textContent = "Ready to download...";
  });
});
