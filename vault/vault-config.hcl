# ShieldAI — HashiCorp Vault Production Configuration
# Deploy with: vault server -config=/vault/config/vault-config.hcl
# NEVER run Vault in -dev mode in production.

# ---------------------------------------------------------------
# Storage — Raft integrated storage (no external Consul needed)
# ---------------------------------------------------------------
storage "raft" {
  path    = "/vault/data"
  node_id = "vault-node-1"

  # Increase snapshot threshold for low-churn SOC secrets
  performance_multiplier = 1
}

# ---------------------------------------------------------------
# Listener — TLS enforced; plaintext only on loopback for health checks
# ---------------------------------------------------------------
listener "tcp" {
  address            = "0.0.0.0:8200"
  tls_cert_file      = "/vault/tls/vault.crt"
  tls_key_file       = "/vault/tls/vault.key"
  tls_min_version    = "tls12"
  # Allow health endpoint over HTTP on localhost only for Docker health checks
  tls_disable_client_certs = true
}

listener "tcp" {
  address     = "127.0.0.1:8201"
  tls_disable = true  # health check endpoint only — never exposed externally
}

# ---------------------------------------------------------------
# Cluster addresses
# ---------------------------------------------------------------
api_addr     = "https://vault:8200"
cluster_addr = "https://vault:8201"

# ---------------------------------------------------------------
# UI — enable for ops convenience; gate behind network policy
# ---------------------------------------------------------------
ui = true

# ---------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = true
}

# ---------------------------------------------------------------
# Seal — uncomment and configure one of the following for auto-unseal
# ---------------------------------------------------------------
# AWS KMS auto-unseal (recommended for cloud deployments):
# seal "awskms" {
#   region     = "us-east-1"
#   kms_key_id = "YOUR_KMS_KEY_ID"
# }

# GCP CKMS auto-unseal:
# seal "gcpckms" {
#   project    = "your-gcp-project"
#   region     = "global"
#   key_ring   = "vault-keyring"
#   crypto_key = "vault-key"
# }
