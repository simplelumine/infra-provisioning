# Architecture & Refactoring Review - 2025-12-08

## Overview
This document summarizes the architectural decisions, refactoring efforts, and technical discussions conducted on December 8, 2025. The session focused on solidifying the Ansible infrastructure capability, clarifying the network topology, and establishing a robust security model for the Hybrid Cloud environment.

## 1. Ansible Refactoring (Infrastructure as Code)

### Variable Scope Optimization
*   **Problem**: `k3s_install_version` was global, preventing independent upgrades of Lab and Prod clusters.
*   **Solution**: Moved version pinning to `group_vars/lab_cluster.yml` and `group_vars/prod_cluster.yml`.
*   **Principle**: Configuration values should live at the scope where they diverge (Cluster-level), not globally.

### K3s Role Architecture
*   **Decision**: **Unified Role with Dynamic Logic** (vs. Split Roles).
*   **Rationale**: Splitting `k3s_control` into `leader` and `follower` folders creates significant code duplication (CNI configs, Kubelet args).
*   **Implementation**: A single `k3s_control` role now uses `set_fact` to dynamically generate installation arguments:
    *   **Leader**: `--cluster-init`
    *   **Follower**: `--server https://... --token ...`
*   **Benefit**: Reduces maintenance burden. Changing a Kubelet arg now only requires editing one line in one file.

### Xray Deployment
*   **Change**: Deployed Xray to **ALL** nodes (Control, Worker, Edge), not just Edge.
*   **Goal**: Enable a full-mesh proxy capability where any node can serve as an ingress/egress point if needed.

## 2. Security & Trust Code

### Firewall Trust Model (OS Level)
*   **Strategy**: **"Trusted Infrastructure"**.
*   **Implementation**: The `firewall` role now iterates over `groups['all']` to whitelist IPs of all managed inventory nodes *if* `firewall_enable_cluster_trust` is true.
*   **Result**: Cluster nodes automatically trust Edge nodes and other Cluster nodes on all ports at the OS layer (iptables). Granular service access is then delegated to Cilium (CNI) and Service definitions.

### Xray Multi-User Security
*   **Concept**: **Single Private Key, Multiple UUIDs**.
*   **Validation**: Confirmed that sharing a VLESS/Reality Private Key is secure. The key authenticates the *Server* (preventing MITM), while the UUID authenticates the *User*.
*   **Scalability**: Adding users is simply appending UUIDs to the `xray_clients` list in Ansible variables.

## 3. Network Architecture (The Core Debate)

### The Dilemma: Edge-to-Cluster Connectivity
How should Edge nodes (e.g., in CN/Asia) transmit reverse-proxy data to the Core Cluster (e.g., in US/EU)?
1.  **Option A: Through Tailscale** (Overlay VPN).
2.  **Option B: Direct Public IP** (HTTPS).

### The Decision: Public IP (Option B)
We chose to utilize the Public IPs for the Data Plane.

*   **Reason 1: Performance**: Tailscale (Userspace WireGuard) introduces MTU overhead and CPU context switching. Public IP (Kernel TCP/IP) offers the lowest latency and highest throughput.
*   **Reason 2: Simplicity**: Avoiding "Tunnel-in-Tunnel" (Cilium inside Tailscale) prevents MTU fragmentation issues and complex debugging.
*   **Reason 3: Security Parity**:
    *   **Tailscale**: Security via Key Authentication.
    *   **Public IP**: Security via Firewall Whitelisting + HTTPS/TLS Encryption.
    *   Both are secure. Since we have static IPs, Firewall Whitelisting is robust.
*   **Role of Tailscale**: Degraded to **Admin/Management Plane**. It serves as a secure "backdoor" for SSH access and Kube API debugging, but does not carry user traffic.

## 4. Edge Reverse Proxy Strategy

### Software Selection
*   **Choice**: **Nginx**.
*   **Why**: Industry standard, highest performance for static proxying, fine-grained control over headers and streams.

### Domain Mapping (Host Header Rewrite)
*   **Scenario**: User visits `st-us.example.com` (Edge), but Cluster serves `st.example.com`.
*   **Mechanism**:
    ```nginx
    proxy_pass https://<Cluster_Public_IP>;
    proxy_set_header Host st.example.com;  # <--- The Magic
    proxy_ssl_server_name on;
    proxy_ssl_name st.example.com;
    ```
*   **Flow**: The Edge node terminates the user's TLS, re-encrypts the traffic, and "spoofs" the Host header so the Cluster's Ingress Controller routes the request to the correct Service.

## 5. Next Steps
*   **Implementation**: Create an `nginx_edge` Ansible role to automate the Edge Gateway configuration.
*   **Observability**: Plan for Prometheus/Grafana integration to monitor this hybrid architecture.
