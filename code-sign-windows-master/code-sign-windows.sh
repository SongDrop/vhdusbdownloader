#!/usr/bin/env bash

# ====== Editable signing parameters ======

SIGN_NAME="rtxdevstation"
SIGN_URL="https://rtxdevstation.xyz/"
TIMESTAMP_URL="http://timestamp.comodoca.com/authenticode"

# ========================================

echo "Signing windows.exe app so Windows don't say its a virus"
echo "For official certificates, you can purchase from DigiCert: https://www.digicert.com"
echo "Or from Sectigo: https://sectigo.com"
echo "Or from GlobalSign: https://www.globalsign.com"
echo "Note: Official code signing certificates typically cost around \$1000 per app."

# ======  Prequisities Uses generated certificates in /certs ======
#certs/ca.crt
#certs/ca.key
#certs/sign.crt
#certs/sign.key

set -exuo pipefail


input_file=$1

if [ ! -f "$input_file" ]; then
  echo 'First argument must be path to binary'
  exit 1
fi

# Check that input file is a windows PE (Portable Executable)
if ! ( file "$input_file" | grep -q PE ); then
  echo 'File must be a Portable Executable (PE) file.'
  exit 0
fi

# Check that osslsigncode is installed
if ! command -v osslsigncode >/dev/null 2>&1 ; then
  echo "osslsigncode utility is not present or missing from PATH. Binary cannot be signed."
  exit 1
fi

orig_file="${input_file}_unsigned"
mv "$input_file" "$orig_file"

osslsigncode sign \
  -certs "./certs/sign.crt" \
  -key "./certs/sign.key" \
  -n "$SIGN_NAME" \
  -i "$SIGN_URL" \
  -t "$TIMESTAMP_URL" \
  -in "$orig_file" \
  -out "$input_file"

rm "$orig_file"
