# ShieldAI Vault Dev Config — NOT for production use
# Uses file storage instead of Raft for simplicity in local dev
storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true  # TLS disabled for local dev only
}

api_addr = "http://vault:8200"
ui       = true
