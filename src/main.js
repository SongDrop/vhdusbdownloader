const {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
  powerSaveBlocker,
} = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const fs = require("fs");
const { shell } = require("electron");

let mainWindow;
let currentDownloaderProcess = null;
let blockerId = null;
let downloadDestPath = null;
let downloadVhdFilename = null;

// Enforce a single application instance
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on("second-instance", (event, commandLine, workingDirectory) => {
    // Someone tried to run a second instance, we should focus our window.
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  function createWindow() {
    const isWindows = process.platform === "win32";
    const iconPath = isWindows
      ? path.join(__dirname, "icon.ico")
      : process.platform === "darwin"
      ? path.join(__dirname, "icon.icns")
      : path.join(__dirname, "icon.png");

    mainWindow = new BrowserWindow({
      minWidth: 700,
      minHeight: 500,
      width: 700,
      height: 500,
      icon: iconPath,
      webPreferences: {
        nodeIntegration: true,
        contextIsolation: false,
      },
    });

    const indexPath = path.join(__dirname, "index.html");
    mainWindow.loadFile(indexPath).catch((err) => {
      console.error("Failed to load index.html:", err);
    });

    mainWindow.on("close", () => app.quit());
  }

  app.whenReady().then(createWindow);

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });

  // IPC Handlers
  ipcMain.handle("select-dest", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openDirectory"],
    });
    if (result.canceled) return null;
    return result.filePaths[0];
  });

  ipcMain.on("start-download", (event, url, destPath) => {
    if (currentDownloaderProcess) {
      event.sender.send("download-log", "A download is already in progress.");
      return;
    }

    blockerId = powerSaveBlocker.start("prevent-app-suspension");

    // Store the destination path and filename for later use
    downloadDestPath = path.dirname(destPath);
    downloadVhdFilename = path.basename(destPath);

    let binaryPath;
    if (app.isPackaged) {
      binaryPath =
        process.platform === "win32"
          ? path.join(process.resourcesPath, "usb_downloader.exe")
          : path.join(process.resourcesPath, "usb_downloader");
    } else {
      binaryPath = path.join(
        __dirname,
        "dist",
        process.platform === "win32" ? "usb_downloader.exe" : "usb_downloader"
      );
    }

    console.log(`Binary path: ${binaryPath}`);

    if (!fs.existsSync(binaryPath)) {
      const errorMessage = `ERROR: Downloader binary not found at ${binaryPath}`;
      console.error(errorMessage);
      event.sender.send("download-log", errorMessage);
      powerSaveBlocker.stop(blockerId);
      blockerId = null;
      return;
    }

    if (process.platform !== "win32") {
      try {
        fs.chmodSync(binaryPath, 0o755);
      } catch (err) {
        const errorMessage = `ERROR: Failed to set executable permissions: ${err.message}`;
        console.error(errorMessage);
        event.sender.send("download-log", errorMessage);
        powerSaveBlocker.stop(blockerId);
        blockerId = null;
        return;
      }
    }

    try {
      const downloader = spawn(binaryPath, [url, destPath]);
      currentDownloaderProcess = downloader;

      downloader.stdout.on("data", (data) => {
        data
          .toString()
          .split("\n")
          .forEach((line) => {
            if (line.trim().length > 0) {
              event.sender.send("download-log", line);
            }
          });
      });

      downloader.stderr.on("data", (data) => {
        data
          .toString()
          .split("\n")
          .forEach((line) => {
            if (line.trim().length > 0) {
              event.sender.send("download-log", line);
            }
          });
      });

      downloader.on("close", (code) => {
        currentDownloaderProcess = null;
        // Pass the code, path, and filename back to the renderer
        event.sender.send(
          "download-done",
          code,
          downloadDestPath,
          downloadVhdFilename
        );

        if (blockerId && powerSaveBlocker.isStarted(blockerId)) {
          powerSaveBlocker.stop(blockerId);
          blockerId = null;
        }
      });

      downloader.on("error", (err) => {
        const errorMessage = `Failed to start subprocess: ${err.message}`;
        console.error(errorMessage);
        event.sender.send("download-log", `ERROR: ${errorMessage}`);

        currentDownloaderProcess = null;
        if (blockerId && powerSaveBlocker.isStarted(blockerId)) {
          powerSaveBlocker.stop(blockerId);
          blockerId = null;
        }
      });
    } catch (err) {
      const errorMessage = `Failed to start downloader process: ${err.message}`;
      console.error(errorMessage);
      event.sender.send("download-log", `ERROR: ${errorMessage}`);

      currentDownloaderProcess = null;
      if (blockerId && powerSaveBlocker.isStarted(blockerId)) {
        powerSaveBlocker.stop(blockerId);
        blockerId = null;
      }
    }
  });

  ipcMain.on("stop-download", (event) => {
    if (currentDownloaderProcess) {
      console.log("Stopping download process...");
      currentDownloaderProcess.kill("SIGINT");

      setTimeout(() => {
        if (currentDownloaderProcess && !currentDownloaderProcess.killed) {
          console.log("Force-killing download process...");
          currentDownloaderProcess.kill("SIGKILL");
          event.sender.send("download-log", "Download forcefully stopped.");
          currentDownloaderProcess = null;
        }
      }, 5000);

      event.sender.send("download-log", "Download stopped by user.");
    } else {
      event.sender.send("download-log", "No download in progress.");
    }
  });

  ipcMain.on("create-vmc-file", (event, destPath, vhdFilename) => {
    if (!destPath || !vhdFilename) {
      console.error("Destination path or VHD filename is missing.");
      return;
    }

    const vhdFilePath = path.join(destPath, vhdFilename);
    const vmcContent = `<?xml version="1.0" encoding="UTF-8"?>
<preferences>
<version type="string">2.0</version>
<hardware>
<pci_bus>
<ide_adapter>
<ide_controller id="0">
<location id="0">
<drive_type type="integer">1</drive_type>
<pathname>
<absolute type="string">${vhdFilePath}</absolute>
<relative type="string">${vhdFilename}</relative>
</pathname>
</location>
</ide_controller>
</ide_adapter>
</pci_bus>
</hardware>
</preferences>`;

    const vmcFilePath = path.join(
      destPath,
      `${path.parse(vhdFilename).name}.vmc`
    );

    fs.writeFile(vmcFilePath, vmcContent, (err) => {
      if (err) {
        console.error("Failed to create VMC file:", err);
        event.sender.send("download-log", "❌ Error creating VMC file.");
      } else {
        console.log(`Successfully created VMC file at: ${vmcFilePath}`);
        event.sender.send(
          "download-log",
          `✅ VMC file created at: ${vmcFilePath}`
        );
      }
    });
  });

  // Listener to handle successful downloads and trigger post-download tasks
  ipcMain.on("download-done", (event, code, destPath, vhdFilename) => {
    if (code === 0) {
      // Create the VMC file automatically after a successful download
      ipcMain.emit("create-vmc-file", event, destPath, vhdFilename);

      // Create and open the README guide
      createAndOpenGuide(destPath);
    }
  });

  function createAndOpenGuide(destPath) {
    const guideContent = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>✅ Your Download is Complete!</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                background-color: #f4f7f9;
            }

            .container {
                background-color: #fff;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
            }

            h1 {
                text-align: center;
                color: #2c3e50;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                margin: 20px;
            }

            h1 img {
                width: 80px;
            }

            h2 {
                color: #2c3e50;
                border-bottom: 2px solid #bdc3c7;
                padding-bottom: 10px;
                margin-top: 30px;
                display: flex;
                align-items: center;
            }

            h2 img {
                margin-right: 10px;
                width: 60px;
            }

            .section {
                margin-bottom: 30px;
            }

            .callout {
                background-color: #e8f7ec;
                border-left: 5px solid #2ecc71;
                padding: 15px;
                border-radius: 6px;
                margin-top: 20px;
                font-size: 1.1em;
            }

            .warning {
                background-color: #fcf8e3;
                border-left: 5px solid #f39c12;
                padding: 15px;
                border-radius: 6px;
                margin-top: 20px;
                font-size: 1em;
            }

            a {
                color: #3498db;
                text-decoration: none;
            }

            a:hover {
                text-decoration: underline;
            }

            ol {
                padding-left: 20px;
            }

            li {
                margin-bottom: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1><img src="https://i.postimg.cc/9MNYQbWF/vhdusbdownloader.png" alt="VHDUSB Downloader Logo" class="app-icon">
                ✅ Your Download is Complete!</h1>
            <p>Your VHD file has been successfully downloaded. This guide will help you with the next steps, whether you're
                using a **Windows PC** or a **macOS** computer.</p>
            <div class="callout">
                🎉 You can find your new files in the destination folder you selected:
                <br><strong><code>${destPath}</code></strong>
            </div>
            <div class="section">
                <h2><img src="https://i.postimg.cc/HsFzgWj9/macosx.png" alt="MacOSX Icon" class="os-icon">For
                    macOS Users</h2>
                <p>VHD files are not natively supported on macOS. To use the downloaded file, you'll need a virtualization
                    application like Parallels Desktop. We've created a special configuration file to make this process
                    simple for you.</p>
                <ol>
                    <li><strong>Install Parallels Desktop:</strong> If you don't have it, you can download a trial or
                        purchase it from the <a href="https://www.parallels.com/products/desktop/" target="_blank">official
                            Parallels website</a>.</li>
                    <li><strong>Locate and Run the File:</strong> In your download folder, you will find two files: the
                        **VHD file** itself and a smaller **.vmc file**. Simply **double-click the <code>.vmc</code> file**.
                    </li>
                    <li><strong>Follow the Parallels Prompts:</strong> Parallels will automatically launch and guide you
                        through the process of creating a new virtual machine from the VHD.</li>
                </ol>
                <div class="warning">
                    <strong>⚠️ Important Note on Disk Space:</strong>
                    <p>During the import, Parallels will create a new, native disk file on your Mac. This means you will
                        need enough free space to **duplicate the VHD file**. For example, if your VHD is 220GB, you will
                        need at least 220GB of free space on your Mac's hard drive to complete the process.</p>
                </div>
            </div>
            <div class="section">
                <h2><img src="https://i.postimg.cc/1zwYTnHF/windows-hyperv.png" alt="Windows Hyper-V Icon"
                        class="os-icon">For Windows Users</h2>
                <p>Windows has built-in support for VHD files through **Hyper-V**. You can use the downloaded VHD to create
                    a bootable virtual machine directly.</p>
                <ol>
                    <li><strong>Enable Hyper-V:</strong> Ensure the Hyper-V feature is enabled on your Windows PC. You can
                        do this in "Turn Windows features on or off" in the Control Panel.</li>
                    <li><strong>Create a New Virtual Machine:</strong> Open the **Hyper-V Manager**, select "New" > "Virtual
                        Machine," and follow the wizard.</li>
                    <li><strong>Connect the VHD:</strong> When prompted to connect a virtual hard disk, select the option to
                        "Use an existing virtual hard disk" and browse to your downloaded VHD file.</li>
                </ol>
            </div>
            <div class="section">
                <h2><img src="https://i.postimg.cc/vm8sdwPX/paralleldesktop.png" alt="Parallels Desktop Icon"
                        class="os-icon">Older Versions of Parallels Desktop</h2>
                <p>If you are using an older version of macOS, you may need an older version of Parallels Desktop for
                    compatibility. Below are some links to older versions:</p>
                <ul>
                    <li><strong>macOS 12:</strong> <a
                            href="https://parallels-desktop.macupdate.com/app/mac/21252/parallels-desktop/old-versions">Parallels
                            16.1.3</a> (Feb 05, 2021)</li>
                    <li><strong>macOS 10.13.6:</strong> <a
                            href="https://parallels-desktop.macupdate.com/app/mac/21252/parallels-desktop/old-versions">Parallels
                            15.1.4</a> (Apr 22, 2020)</li>
                    <li><strong>macOS 10.12.6:</strong> <a
                            href="https://parallels-desktop.macupdate.com/app/mac/21252/parallels-desktop/old-versions">See
                            old versions link</a></li>
                </ul>
                <p><strong>Note:</strong> You can find more versions at the <a
                        href="https://parallels-desktop.macupdate.com/app/mac/21252/parallels-desktop/old-versions"
                        target="_blank">MacUpdate page</a>.</p>
            </div>
        </div>
    </body>
    </html>
    `;
    const guidePath = path.join(destPath, "README.html");
    fs.writeFile(guidePath, guideContent, (err) => {
      if (err) {
        console.error("Failed to create HTML guide:", err);
        return;
      }
      shell.openPath(guidePath); // Opens the HTML file in the user's default browser
    });
  }
}
