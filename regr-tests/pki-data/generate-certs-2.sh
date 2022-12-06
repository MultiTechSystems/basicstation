#!/bin/bash

CANAME=MyOrg-RootCA
# optional, create a directory
mkdir $CANAME
cd $CANAME
# generate aes encrypted private key
openssl genrsa -passout pass:"hello" -aes256 -out $CANAME.key 4096 
# create certificate, 1826 days = 5 years
openssl req -x509 -new -passin pass:"hello" -nodes -key $CANAME.key -sha256 -days 3650 -out $CANAME.crt -subj '/CN=Root CA/C=AT/ST=MN/L=MN/O=Multitech'
# create certificate for service
MYCERT=myserver.local
openssl req -new -nodes -out $MYCERT.csr -newkey rsa:4096 -keyout $MYCERT.key -subj '/CN=BSTEST/C=AT/ST=MN/L=MN/O=Multitech' 
# create a v3 ext file for SAN properties
cat > $MYCERT.v3.ext << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:TRUE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names
[alt_names]
DNS = localhost 
EOF

openssl x509 -req -in $MYCERT.csr -passin pass:'hello' -CA $CANAME.crt -CAkey $CANAME.key -CAcreateserial -out $MYCERT.crt -days 3650 -sha256 -extfile $MYCERT.v3.ext -passin pass:'hello'
