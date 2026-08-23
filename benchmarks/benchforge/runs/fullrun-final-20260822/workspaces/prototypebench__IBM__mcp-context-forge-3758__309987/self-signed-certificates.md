# Self-Signed Certificates for mTLS

## Overview

This document describes how to generate and use self-signed certificates for mutual TLS (mTLS) authentication.

## Generating Self-Signed Certificates

### 1. Generate Root CA
```bash
openssl req -x509 -newkey rsa:4096 -keyout ca.key -out ca.crt -days 3650 -nodes -subj "/CN=MyRootCA"
```

### 2. Generate Server Certificate
```bash
openssl req -newkey rsa:4096 -keyout server.key -out server.csr -nodes -subj "/CN=localhost"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365
```

### 3. Generate Client Certificate
```bash
openssl req -newkey rsa:4096 -keyout client.key -out client.csr -nodes -subj "/CN=client"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 365
```

## Configuration

In your gateway configuration, provide:
- `client_cert`: The client certificate (client.crt)
- `client_key`: The client private key (client.key)
- `ca_certificate`: The CA certificate (ca.crt)

## Security Considerations
- Store private keys securely
- Use appropriate key sizes (RSA 2048+ or ECDSA P-256+)
- Rotate certificates before expiration
- Validate certificate chains properly
