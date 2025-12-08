# Edge Routing & Cluster Security Architecture Discussion

## Context
We are designing the traffic flow for a hybrid infrastructure consisting of:
- **Edge Nodes** (e.g., DMIT CN2GIA in Hong Kong) for optimized China access.
- **Cluster Nodes** (US-based K3s Cluster) hosting the actual applications.
- **Cloudflare** for global traffic acceleration and protection.
- **Tailscale** for internal mesh networking.

## Core Architectural Decisions

### 1. Traffic Routing Strategy (Hybrid Model)

We adopted a hybrid routing strategy to maximize performance and availability:

*   **Global Users**: Hit **Cloudflare** -> **Cluster Public IP**.
*   **China Users**: Hit **Edge Node (CN2GIA)** -> **Cluster Public IP**.

**Key Decision: Why Public IP for Edge-to-Cluster?**
Initially, we considered using Tailscale for the link between Edge and Cluster. However, we decided to use **Public IP with Host Header Injection** because:
- **Performance**: High-throughput public network handling without the CPU overhead of VPN encryption/decryption.
- **Simplicity**: Since the Cluster ports (80/443) must be open for Cloudflare anyway, using them for the Edge node avoids maintaining a separate VPN tunnel dependency for production traffic.
- **Redundancy**: If Tailscale goes down, production traffic remains unaffected.

### 2. Upstream Configuration (Load Balancing)

The Edge Node (Caddy) is configured to load balance traffic across **multiple Cluster Worker Nodes**.

**Changes in `host_vars/lab-hkg-eg1.yml`**:
```yaml
caddy_sites:
  - domain: "st-us.xxx.com"
    # Load balance across all worker nodes for high availability
    upstream: "https://1.1.1.1:443 https://2.2.2.2:443 https://3.3.3.3:443"
    # Forge the Host header to match the Ingress rule on the cluster
    host_header: "st.xxx.com"
```

### 3. Security & Port Exposure (The "Open Gate" Trade-off)

We analyzed the trade-off between closing all ports (Tunnel-only) vs. opening Ports 80/443.

**Decision: Open Ports 80/443**
We chose to keep ports 80 and 443 open on the Cluster nodes to support standard Cloudflare proxying and Direct Edge access.

**Security Mitigation**:
To prevent unauthorized scanning or attacks on the Source IP:
- **Application Layer**: Cilium Network Policies (Future implementation) to restrict Ingress traffic.
- **Network Layer (Recommended)**: Configure Firewall/Security Group Allow-lists to **ONLY** accept traffic on 80/443 from:
    1.  **Cloudflare IP Ranges**: https://www.cloudflare.com/ips/
    2.  **Our Edge Node Public IPs**
    3.  **Deny All** other sources.

This achieves "virtual invisibility" while maintaining a standard, robust network architecture.

### 4. Ansible Configuration Logic

*   **`host_vars` vs `group_vars`**: We moved site definitions to `host_vars` to allow per-node configuration (e.g., HKG node proxies `st-us`, LAX node proxies `st-la`).
*   **Role Defaults**: We kept `defaults/main.yml` in the Caddy role to ensure playbook stability (crash safety) even if variables are missing for a new host.
