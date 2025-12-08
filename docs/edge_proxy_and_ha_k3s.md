# Architecture Decision: Edge Proxy and K3s HA Mode

**Status**: Implemented
**Date**: 2025-12-08

## 1. K3s HA Mode (Etcd vs SQLite)

### Context
K3s defaults to embedded Etcd when using `--cluster-init`. While robust, Etcd is resource-intensive (I/O sensitive) and unnecessary for single-node environments (Lab/Dev) or resource-constrained nodes.

### Decision
Introduced a variable `k3s_etcd_mode: true/false`.
- **True (Default/Prod)**: Uses `--cluster-init`. Enables embedded HA Etcd. Allows adding more control plane nodes.
- **False (Lab/Single)**: Uses standard K3s behavior (SQLite). Significantly lower memory/CPU footprint. **Constraint**: Doesn't support multiple control plane nodes.

### Implementation
- `group_vars/all/vars.yml`: `k3s_etcd_mode: true` (Default)
- `roles/k3s_control`: Logic checks this variable to append/omit flag.

---

## 2. Edge Proxy Selection

### Context
Edge nodes (CN2 GIA/1G) need to accelerate traffic for China-based users and proxy it back to the origin cluster. The user requires **Security (No plain HTTP transport)** and performance optimization.

### Options Analyzed
1.  **Nginx**: Industrial standard, but config is verbose and HTTP/3 support requires setup. Certificate management (Let's Encrypt) is manual/external (Certbot).
2.  **Traefik**: Great for dynamic backends, but overkill for static edge proxying. Config can be complex.
3.  **Caddy (Selected)**:
    - **Automatic HTTPS**: Zero-config Let's Encrypt.
    - **HTTP/3 by Default**: Critical for cross-border acceleration (UDP/QUIC outperforms TCP in high-latency links).
    - **Simplicity**: `reverse_proxy` directive is extremely concise.

### Architecture Design
- **Public Entry**: Caddy listens on 443 (HTTP/3 + HTTP/2). Auto-terminates TLS.
- **Upstream Transport**:
    - Requirement: **No plaintext HTTP** on the wire.
    - Implementation: Caddy proxies via **HTTPS** to the Origin Ingress.
    - `reverse_proxy https://<Cluster_VIP>`
- **Role Name**: `caddy` (formerly `edge_proxy`).
