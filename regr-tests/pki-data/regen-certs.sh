#!/bin/bash
# Regenerate PKI certificates for regression tests
# Certificates valid for 10 years

set -e
cd "$(dirname "$0")"

DAYS=3650  # 10 years

# Create Root CA
echo "Creating Root CA..."
openssl genrsa -out rootCA.key 4096
openssl req -x509 -new -nodes -key rootCA.key -sha256 -days $DAYS \
    -subj "/C=US/OU=Semtech/O=semtech.com/CN=Root CA" \
    -out rootCA.crt

# Function to create a server certificate with SAN for localhost
create_cert() {
    local name=$1
    local cn=$2
    
    echo "Creating certificate for $name (CN=$cn)..."
    
    # Generate key
    openssl genrsa -out ${name}.key 2048
    
    # Create CSR
    openssl req -new -key ${name}.key \
        -subj "/C=US/OU=Semtech/O=semtech.com/CN=$cn" \
        -out ${name}.csr
    
    # Create extension file for SAN
    cat > ${name}.ext << EOF
subjectAltName = DNS:localhost
EOF
    
    # Sign with Root CA (including SAN extension)
    openssl x509 -req -in ${name}.csr -CA rootCA.crt -CAkey rootCA.key \
        -CAcreateserial -out ${name}.crt -days $DAYS -sha256 \
        -extfile ${name}.ext
    
    # Copy CA cert for trust
    cp rootCA.crt ${name}.ca
    
    # Cleanup
    rm ${name}.csr ${name}.ext
}

# Create all server certificates
create_cert "infos-0" "infos-::0"
create_cert "muxs-0" "muxs-::0"
create_cert "cups-0" "cups-::0"
create_cert "tc-router-1" "tc-router-1"
create_cert "tc-router-2" "tc-router-2"
create_cert "cups-router-1" "cups-router-1"
create_cert "cups-router-2" "cups-router-2"

# Cleanup
rm -f rootCA.srl

echo "Done! Certificates regenerated with $DAYS days validity."
echo "New expiration: $(openssl x509 -in infos-0.crt -noout -enddate)"
