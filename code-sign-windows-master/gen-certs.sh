#!/usr/bin/env bash

# ====== Editable certificate details ======

# CA certificate details
CA_COUNTRY="GB"
CA_STATE="United Kingdom"
CA_CITY="London"
CA_ORG="rtxdevstation.xyz"
CA_UNIT="open-source-development"
CA_COMMON_NAME="rtxdevstation"

# Signing certificate details
SIGN_COUNTRY="US"
SIGN_STATE="United Kingdom"
SIGN_CITY="London"
SIGN_ORG="rtxdevstation.xyz"
SIGN_UNIT="open-source-development"
SIGN_COMMON_NAME="rtxdevstation"


# ====== Generates certificate an save in /certs ======
#ca.crt
#ca.key
#sign.crt
#sign.key

set -exuo pipefail


# Build subject strings
CA_SUBJECT="/C=${CA_COUNTRY}/ST=${CA_STATE}/L=${CA_CITY}/O=${CA_ORG}/OU=${CA_UNIT}/CN=${CA_COMMON_NAME}"
SIGNING_SUBJECT="/C=${SIGN_COUNTRY}/ST=${SIGN_STATE}/L=${SIGN_CITY}/O=${SIGN_ORG}/OU=${SIGN_UNIT}/CN=${SIGN_COMMON_NAME}"

# ==========================================

mkdir -p certs

# Certificate authority (CA)
openssl genrsa -out certs/ca.key 2048
openssl req -new -x509 -nodes -days 1000 -key certs/ca.key -out certs/ca.crt -subj "$CA_SUBJECT"

# Generate a certificate for code signing, signed by the CA
openssl req -newkey rsa:2048 -nodes -keyout certs/sign.key -out certs/sign.req -subj "$SIGNING_SUBJECT"
openssl x509 -req -in certs/sign.req -days 398 -CA certs/ca.crt -CAkey certs/ca.key -set_serial 01 -out certs/sign.crt

# Clean up
rm certs/sign.req
