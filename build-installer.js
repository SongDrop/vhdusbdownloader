const electronInstaller = require("electron-winstaller");
const path = require("path");

// Installer configuration
const CONFIG = {
  authors: "RtxDevstation",
  exeName: "vhdusbdownloader.exe",
  iconPath: path.join(__dirname, "build", "usb_icon.ico"),
  setupExe: "vhdusbdownloaderInstaller.exe",
  setupDescription: "vhdusbdownloader Electron App",
  appDir: path.join(__dirname, "dist", "win-unpacked"),
  outputDir: path.join(__dirname, "installer"),
};

async function buildInstaller() {
  try {
    await electronInstaller.createWindowsInstaller({
      appDirectory: CONFIG.appDir, // Path to unpacked Electron app
      outputDirectory: CONFIG.outputDir, // Where installer will be generated
      authors: CONFIG.authors, // Author info
      exe: CONFIG.exeName, // Main executable name
      iconUrl: CONFIG.iconPath, // Optional URL for installer icon
      setupIcon: CONFIG.iconPath, // Local icon for setup.exe
      noMsi: true, // Skip MSI installer creation
      setupExe: CONFIG.setupExe, // Installer output file name
      description: CONFIG.setupDescription,
    });
    console.log("Installer created successfully!");
  } catch (e) {
    console.error("Error creating installer:", e.message);
  }
}

buildInstaller();
