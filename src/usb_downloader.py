import urllib3
import time
from tqdm import tqdm
import os
import sys
import shutil
import signal
import atexit
import logging
from urllib.parse import urlparse
from filelock import FileLock
import socket
import subprocess
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Azure imports - only for authenticated access
try:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient, BlobClient, BlobProperties
    from azure.core.exceptions import HttpResponseError
    # Disable Azure SDK debug logging
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("azure.identity").setLevel(logging.WARNING)
    logging.getLogger("azure.storage").setLevel(logging.WARNING)
    AZURE_SDK_AVAILABLE = True
except ImportError:
    AZURE_SDK_AVAILABLE = False

# Disable insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up logging
logger = None
log_file_path = None

# Determine the correct lock file path based on OS
if sys.platform == "win32":
    lock_file = os.path.join(os.environ["APPDATA"], "usb_downloader.lock")
elif sys.platform == "darwin":
    lock_file = os.path.join("/tmp", "usb_downloader.lock")
else:
    lock_file = os.path.join("/tmp", "usb_downloader.lock")

lock = FileLock(lock_file)

class AzureBlobDownloader:
    def __init__(self):
        self.chunk_size = 64 * 1024 * 1024  # 64MB chunks for better performance
        self.download_interrupted = False
        
    def is_azure_url(self, url):
        """Check if URL is from Azure Blob Storage"""
        return url and '.blob.core.windows.net' in url

    def get_blob_client(self, blob_url):
        """Create a BlobClient - try without auth first, then with auth if needed"""
        try:
            # First try without authentication (for public blobs)
            try:
                blob_client = BlobClient.from_blob_url(blob_url)
                # Test if it's accessible without auth
                blob_client.get_blob_properties()
                logger.info("✅ Blob is publicly accessible - no authentication needed")
                return blob_client
            except HttpResponseError as e:
                if e.status_code == 401 or e.status_code == 403:
                    logger.info("🔐 Blob requires authentication, trying with credentials...")
                    # Try with authentication
                    credential = DefaultAzureCredential()
                    blob_client = BlobClient.from_blob_url(blob_url, credential=credential)
                    blob_client.get_blob_properties()  # Test access
                    return blob_client
                else:
                    raise e
                    
        except Exception as e:
            logger.error(f"Error creating blob client: {e}")
            return None

    def download_blob(self, blob_url, destination_path):
        """Download blob using Azure SDK or fallback to direct download"""
        logger.info("🚀 Using Azure SDK for Azure Blob Storage download")
        logger.info(f"Source: {blob_url}")
        logger.info(f"Destination: {destination_path}")
        
        # First try with Azure SDK
        blob_client = self.get_blob_client(blob_url)
        
        if blob_client:
            try:
                # Get blob properties to check size
                blob_properties = blob_client.get_blob_properties()
                file_size = blob_properties.size
                logger.info(f"📦 File size: {file_size / (1024**3):.2f} GB")
                
                # Check if file already exists and is complete
                if os.path.exists(destination_path):
                    existing_size = os.path.getsize(destination_path)
                    if existing_size == file_size:
                        logger.info("✅ File already exists and is complete")
                        return True
                    elif existing_size > 0:
                        logger.info(f"↩️ Resuming from {existing_size} bytes")
                
                # Download with progress bar
                with open(destination_path, "wb") as file:
                    download_stream = blob_client.download_blob(
                        max_concurrency=4,  # Parallel connections
                    )
                    
                    # Create progress bar with custom formatting to show only percentage
                    with tqdm(
                        total=file_size,
                        unit='B',
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=os.path.basename(destination_path),
                        mininterval=0.5,  # Update more frequently
                        bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
                        ascii=True
                    ) as pbar:
                        
                        # Download in chunks and update progress
                        for chunk in download_stream.chunks():
                            if self.download_interrupted:
                                logger.warning("⏹️ Download interrupted by user")
                                return False
                                
                            file.write(chunk)
                            pbar.update(len(chunk))
                            
                            # Flush periodically to ensure data is written
                            if pbar.n % (100 * 1024 * 1024) == 0:
                                file.flush()
                                os.fsync(file.fileno())
                
                logger.info("✅ Azure download completed successfully!")
                return True
                
            except Exception as e:
                logger.error(f"❌ Azure SDK download failed: {e}")
                logger.info("🔄 Falling back to direct HTTP download...")
                # Fall through to direct download
        else:
            logger.warning("❌ Azure SDK not available or failed, falling back to direct download")
        
        # Fallback to direct HTTP download for Azure blobs
        return self.download_azure_direct(blob_url, destination_path)

    def download_azure_direct(self, blob_url, destination_path):
        """Direct download for Azure blobs without SDK"""
        logger.info("📡 Using direct HTTP download for Azure blob")
        
        try:
            # Use requests session with proper headers for Azure
            session = requests.Session()
            headers = {
                'x-ms-version': '2020-04-08',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Get file size first
            response = session.head(blob_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            file_size = int(response.headers.get('Content-Length', 0))
            if file_size == 0:
                logger.error("Could not determine file size")
                return False
                
            logger.info(f"📦 File size: {file_size / (1024**3):.2f} GB")
            
            # Check existing file
            existing_size = 0
            if os.path.exists(destination_path):
                existing_size = os.path.getsize(destination_path)
                if existing_size == file_size:
                    logger.info("✅ File already exists and is complete")
                    return True
            
            # Download with progress
            with session.get(blob_url, headers=headers, stream=True, timeout=(30, 300)) as response:
                response.raise_for_status()
                
                mode = 'ab' if existing_size > 0 else 'wb'
                with open(destination_path, mode) as file:

                    # Use larger chunk size for better performance
                    chunk_size = 32 * 1024 * 1024  # 32MB chunks
                    
                    with tqdm(
                        total=file_size,
                        initial=existing_size,
                        unit='B',
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=os.path.basename(destination_path),
                        mininterval=0.5,
                        bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
                        ascii=True
                    ) as pbar:
                        
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if self.download_interrupted:
                                logger.warning("⏹️ Download interrupted by user")
                                return False
                                
                            if chunk:
                                file.write(chunk)
                                pbar.update(len(chunk))
                                
                                if pbar.n % (100 * 1024 * 1024) == 0:
                                    file.flush()
                                    os.fsync(file.fileno())
            
            logger.info("✅ Direct download completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Direct download failed: {e}")
            return False

class USBDownloader:
    def __init__(self):
        self.keep_awake_process = None
        self.download_interrupted = False
        self.session = self._create_session()
        self.azure_downloader = AzureBlobDownloader() if AZURE_SDK_AVAILABLE else None
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def _create_session(self):
        """Create a requests session with robust retry settings"""
        session = requests.Session()
        
        # Custom retry strategy
        retry_strategy = Retry(
            total=20,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            respect_retry_after_header=True
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=100,
            pool_maxsize=100
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session

    def setup_logging(self, dest_path):
        """Set up logging - only show important messages"""
        global logger, log_file_path
        log_dir = os.path.dirname(dest_path) or "."
        log_file = os.path.join(log_dir, "usb_downloader.log")
        log_file_path = log_file
        
        # If the directory isn't writable, fall back to home directory
        if not self.is_path_writable(log_dir):
            home_dir = os.path.expanduser("~")
            log_file = os.path.join(home_dir, "usb_downloader.log")
            print(f"⚠️ Destination directory not writable, using home directory for log: {log_file}")
        
        # Set up logging - only show INFO level and above, suppress debug
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        # Suppress verbose logging from dependencies
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("azure").setLevel(logging.WARNING)
        
        logger = logging.getLogger(__name__)
        logger.info(f"Log file: {log_file}")

    def signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully"""
        if logger:
            logger.info(f"Received interrupt signal ({signum}), cleaning up...")
        self.download_interrupted = True
        if self.azure_downloader:
            self.azure_downloader.download_interrupted = True
        self.cleanup()
        sys.exit(1)

    def prevent_system_sleep(self):
        """Prevent system from sleeping during download"""
        try:
            if logger:
                logger.info("😴 Preventing system sleep during download...")
            if sys.platform == "darwin":
                self.keep_awake_process = subprocess.Popen(["caffeinate", "-dims"])
            elif sys.platform == "win32":
                self.keep_awake_process = subprocess.Popen(["powercfg", "-change", "-standby-timeout-ac", "0"])
            return True
        except Exception as e:
            if logger:
                logger.error(f"Could not prevent system sleep: {e}")
            return False

    def restore_system_sleep(self):
        """Restore normal system sleep behavior"""
        try:
            if self.keep_awake_process:
                self.keep_awake_process.terminate()
                self.keep_awake_process.wait(timeout=5)
            if logger:
                logger.info("😴 Restored normal system sleep behavior")
        except Exception as e:
            if logger:
                logger.error(f"Error restoring sleep settings: {e}")

    def cleanup(self):
        """Cleanup function to restore settings"""
        self.restore_system_sleep()

    def is_path_writable(self, path):
        """Check if the path is writable"""
        try:
            if os.path.exists(path):
                if os.path.isdir(path):
                    test_file = os.path.join(path, ".write_test")
                    with open(test_file, 'w') as f:
                        f.write("test")
                    os.remove(test_file)
                    return True
                else:
                    return self.is_path_writable(os.path.dirname(path))
            else:
                parent_dir = os.path.dirname(path)
                if not os.path.exists(parent_dir):
                    return False
                return self.is_path_writable(parent_dir)
        except (IOError, OSError):
            return False

    def get_drive_space(self, path):
        """Return total and free space in bytes for the given path."""
        try:
            if not os.path.exists(path):
                path = os.path.dirname(path)
            usage = shutil.disk_usage(path)
            return usage.total, usage.free
        except Exception as e:
            if logger:
                logger.error(f"Failed to get drive space: {e}")
            return 0, 0

    def get_remote_file_size(self, url):
        """Get the size of the file from the remote server"""
        try:
            # Use Azure-specific headers for Azure URLs
            headers = {}
            if self.is_azure_url(url):
                headers = {'x-ms-version': '2020-04-08'}
                
            response = self.session.head(url, headers=headers, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            size = response.headers.get("Content-Length") or response.headers.get("x-ms-content-length")
            
            if size is None:
                raise ValueError("Server did not return Content-Length")
            return int(size)
        except Exception as e:
            if logger:
                logger.error(f"Failed to get remote file size: {e}")
            return 0

    def human_readable_size(self, num_bytes):
        """Convert bytes into GB (decimal) and GiB (binary)."""
        gb = num_bytes / 1_000_000_000
        gib = num_bytes / (1024 ** 3)
        return f"{gb:.2f} GB (decimal) / {gib:.2f} GiB (binary)"

    def verify_download(self, dest_path, expected_size):
        """Verify the downloaded file size matches expected size."""
        try:
            actual_size = os.path.getsize(dest_path)
            if actual_size == expected_size:
                logger.info(f"Download verified: {actual_size} bytes")
                return True
            else:
                logger.error(f"Download verification failed: expected {expected_size}, got {actual_size}")
                return False
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return False

    def wait_for_network_recovery(self, hostname, max_wait=300, check_interval=10):
        """Wait for DNS and network recovery after a failure"""
        if logger:
            logger.warning("🌐 Network connection lost. Waiting for recovery...")

        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                socket.getaddrinfo(hostname, 443)
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(5)
                test_socket.connect((hostname, 443))
                test_socket.close()
                
                if logger:
                    logger.info("✅ Network connectivity restored")
                return True
            except (socket.gaierror, socket.timeout, ConnectionError):
                if logger:
                    logger.warning("⏳ Still waiting for network recovery...")
                time.sleep(check_interval)
            except Exception as e:
                if logger:
                    logger.warning(f"⚠️ Error checking network: {e}")
                time.sleep(check_interval)

        if logger:
            logger.error("❌ Network did not recover within timeout period")
        return False

    def download_with_resume(self, url, dest_path, total_size):
        """Download file with resume support for regular HTTP downloads"""
        headers = {}
        existing_size = 0
        
        # Add Azure-specific headers for Azure URLs
        if self.is_azure_url(url):
            headers = {'x-ms-version': '2020-04-08'}
        
        if os.path.exists(dest_path):
            existing_size = os.path.getsize(dest_path)
            if existing_size > 0:
                headers['Range'] = f'bytes={existing_size}-'
                logger.info(f"↩️ Resuming from {existing_size} bytes")

        try:
            with self.session.get(url, headers=headers, stream=True, timeout=(30, 300)) as response:
                response.raise_for_status()
                
                if existing_size > 0 and response.status_code == 200:
                    logger.warning("❌ Server doesn't support resume, starting fresh...")
                    os.remove(dest_path)
                    existing_size = 0
                    response = self.session.get(url, headers=headers, stream=True, timeout=(30, 300))
                    response.raise_for_status()

                mode = 'ab' if existing_size > 0 else 'wb'
                
                with open(dest_path, mode) as file:
                    with tqdm(
                        total=total_size,
                        initial=existing_size,
                        unit='B',
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=os.path.basename(destination_path),
                        mininterval=0.5,
                        bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
                        ascii=True
                    ) as pbar:
                        
                        for chunk in response.iter_content(chunk_size=8*1024*1024):
                            if self.download_interrupted:
                                logger.warning("⏹️ Download interrupted by user")
                                return False
                                
                            if chunk:
                                file.write(chunk)
                                pbar.update(len(chunk))
                                
                                if pbar.n % (100 * 1024 * 1024) == 0:
                                    file.flush()
                                    os.fsync(file.fileno())
                
                return True
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Download error: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return False

    def is_azure_url(self, url):
        """Check if URL is from Azure Blob Storage"""
        return url and '.blob.core.windows.net' in url

    def download_file(self, url, dest_path):
        """Download file from URL to destination path"""
        self.setup_logging(dest_path)
        logger.warning("⚠️  IMPORTANT: This download may take many hours.")
        logger.warning("⚠️  Do NOT shut down or restart your computer during download.")
        logger.warning("⚠️  Ensure stable power and internet connection.")

        logger.info(f"🔗 Starting download from: {url}")
        logger.info(f"⬇️ Destination: {dest_path}")

        # Check if this is an Azure URL
        if self.is_azure_url(url) and self.azure_downloader:
            logger.info("🔷 Azure Blob Storage detected")
            self.azure_downloader.download_interrupted = self.download_interrupted
            return self.azure_downloader.download_blob(url, dest_path)

        if not self.is_path_writable(dest_path):
            logger.error(f"Destination path is not writable: {dest_path}")
            return False

        self.prevent_system_sleep()

        mount_path = os.path.dirname(dest_path) or "/"
        total_space, free_space = self.get_drive_space(mount_path)
        file_size = self.get_remote_file_size(url)
        
        if file_size == 0:
            logger.error("Could not determine file size, using estimated size")
            file_size = 236820000000  # 236.82 GB in bytes
        
        logger.info(f"🧳 Remote file size: {self.human_readable_size(file_size)}")
        logger.info(f"💾 Drive total space: {self.human_readable_size(total_space)}")
        logger.info(f"💿 Free space on drive: {self.human_readable_size(free_space)}")

        # Check existing file
        existing_size = 0
        if os.path.exists(dest_path):
            existing_size = os.path.getsize(dest_path)
            
            if existing_size == file_size:
                logger.info("✅ File already downloaded completely")
                if self.verify_download(dest_path, file_size):
                    return True
            
            if existing_size > file_size:
                logger.warning("⚠️ File appears corrupted, deleting...")
                os.remove(dest_path)
                existing_size = 0

        # Calculate required space correctly
        remaining_size = max(file_size - existing_size, 0)
        required_space = remaining_size * 1.01
        
        if free_space < required_space:
            logger.error(
                f"❌ Not enough free space. "
                f"Required: {self.human_readable_size(required_space)}, "
                f"Available: {self.human_readable_size(free_space)}"
            )
            return False

        if existing_size > 0:
            logger.info("Existing file found. Attempting resume...")

        logger.info(f"📦 Starting download, total size: {self.human_readable_size(file_size)}")

        max_attempts = 10
        for attempt in range(max_attempts):
            success = self.download_with_resume(url, dest_path, file_size)
            
            if success:
                if self.verify_download(dest_path, file_size):
                    logger.info("✅ Download completed and verified successfully!")
                    return True
                else:
                    logger.error("❌ Download completed but verification failed")
                    return False
            else:
                if attempt < max_attempts - 1:
                    wait_time = min(2 ** attempt * 30, 300)
                    logger.warning(f"⏸️ Download failed, waiting {wait_time} seconds before retry {attempt + 2}/{max_attempts}...")
                    time.sleep(wait_time)
                    
                    parsed_url = urlparse(url)
                    self.wait_for_network_recovery(parsed_url.hostname, max_wait=120)
                else:
                    logger.error(f"❌ Download failed after {max_attempts} attempts")
                    return False

        return False


def is_valid_url(url):
    """Check if the URL is valid"""
    if not url:
        return False
    if not url.startswith(('http://', 'https://')):
        return False
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc and parsed.scheme)
    except Exception:
        return False


downloader = USBDownloader()

def main():
    if len(sys.argv) < 3:
        print("Usage: python usb_downloader.py <URL> <DEST_PATH>")
        print("Example: python usb_downloader.py https://example.com/file.vhd /Volumes/USB/file.vhd")
        sys.exit(1)

    url = sys.argv[1]
    dest_path = sys.argv[2]

    print("\n" * 3)
    print("=" * 60)
    print("🚀 USB Downloader Starting...")
    print("=" * 60)

    with lock:
        try:
            if not is_valid_url(url):
                print("❌ Invalid URL. Must start with http:// or https:// and have a valid format.")
                print(f"URL provided: {url}")
                sys.exit(1)
            else:
                print(f"📥 Downloading from: {url}")
                print(f"💾 Saving to: {dest_path}")
                print("⏳ This may take several hours...")
                print("-" * 60)

            success = downloader.download_file(url, dest_path)
            if not success:
                print("❌ Download failed - check the log file for details")
                if log_file_path:
                    print(f"📋 Log file: {log_file_path}")
                sys.exit(1)
            else:
                print("✅ Download completed successfully!")
                if log_file_path:
                    print(f"📋 Log file: {log_file_path}")
        except KeyboardInterrupt:
            print("⏹️ Download interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()