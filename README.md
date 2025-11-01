# VHDUSBDownloader

This is an Electron app that allows you to download large files (like VHD snapshots) directly to USB drives with a GUI, progress tracking, and resume support.

## Features

- Graphical interface for easy downloads
- Shows remote file size, drive total, and free space
- Automatically checks USB/drive space before download
- Supports resuming interrupted downloads
- 1 MB block download with progress bar
- Saves downloads to user-specified folder (USB drives supported)
- Cross-platform (Windows/macOS/Linux)
- Simple tray integration for background downloads (optional)

## Usage

1. Ensure Node.js (v20+) is installed on your system.
2. Run `npm install` to install Electron and dependencies.
3. Start the app with:

```bash
npm start
```

4. Enter the **file URL** and **destination path** (USB drive recommended).
5. Monitor download progress through the GUI.
6. If the download is interrupted, relaunch the app to resume.

## Build & Installer

This project uses Electron to package the app and create platform-specific builds.

### Windows

1. Install build dependencies:

```bash
npm install electron-builder --save-dev
```

2. Build the app for Windows:

```bash
npm run build-win
```

- Output: `./dist/win-unpacked/`

3. Create the Windows installer:

```bash
npm run build-installer
```

- Output: `./installer/VHDUSBDownloaderInstaller.exe`

4. Optionally, sign your executable to reduce Windows security warnings.

5. Generate self-signed Windows certificate to avoid flagging during download:

```bash
cd code-sign-windows-master
chmod +x gen-certs.sh code-sign-windows.sh verify-sign-windows.sh # ensure scripts have execute permission
./gen-certs.sh # generate certificates
./code-sign-windows.sh "yourelectronapp.exe" # sign your exe with certificate
./verify-sign-windows.sh "yourelectronapp.exe" # verify certificate signing
```

- Modify company details in `gen-certs.sh`:

# CA certificate details

```bash
CA_COUNTRY="GB"
CA_STATE="United Kingdom"
CA_CITY="London"
CA_ORG="rtxdevstation.xyz"
CA_UNIT="open-source-development"
CA_COMMON_NAME="rtxdevstation"
```

# Signing certificate details

```bash
SIGN_COUNTRY="US"
SIGN_STATE="United Kingdom"
SIGN_CITY="London"
SIGN_ORG="rtxdevstation.xyz"
SIGN_UNIT="open-source-development"
SIGN_COMMON_NAME="rtxdevstation"
```

### macOS

1. Install build dependencies:

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
export NODE_OPTIONS=--openssl-legacy-provider
node -v
npm -v
npm install electron-builder --save-dev
```

2. Build the app for macOS:

```bash
npm run build-mac
```

- Output: `./dist/mac/` containing `VHDUSBDownloader.app`

3. (Optional) Notarize the app with Apple to avoid security warnings:

```bash
xcrun altool --notarize-app -f ./dist/mac/VHDUSBDownloader.app --primary-bundle-id "com.yourdomain.vhdusbdownloader" -u "APPLE_ID" -p "APP_SPECIFIC_PASSWORD"
```

4. After notarization, staple the ticket to the app:

```bash
xcrun stapler staple ./dist/mac/VHDUSBDownloader.app
```

## Suggested Folder Structure

```bash
vhdusbdownloader/
├─ build/ # Icons, assets
├─ certs/ # Optional certificates for signing
├─ dist/ # Electron build output
├─ src/ # App source code
│ ├─ main.js # Electron main process
│ ├─ renderer.js # GUI renderer code
│ └─ usb_downloader.py # Python download logic
├─ installer/ # Generated installer output
├─ package.json
├─ build-installer.js
└─ README.md
```

## Notes

- Always download large files to drives with sufficient free space.
- The app calculates remaining free space before starting downloads.
- Resuming downloads requires the partial file to remain in the same location.
- Recommended file types: `.vhd`, `.iso`, large archives.
- On macOS, the `.app` bundle can be copied to `/Applications` for easy access.

```bash
python3.10 -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt
```

```bash
cd src
python3 -m venv venv
source venv/bin/activate   # on Mac/Linux
pip install -r requirements.txt
pyinstaller --hidden-import binascii --onefile usb_downloader.py


export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
export NODE_OPTIONS=--openssl-legacy-provider
node -v
npm -v
rm -rf distnpm
npm install
npm run build-mac
```

## License

MIT
