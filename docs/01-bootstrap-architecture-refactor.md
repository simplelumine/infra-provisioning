# Session 01: Bootstrap Architecture Refactoring

**Date:** 2025-12-07
**Topic:** Infrastructure Bootstrap & Security Hardening

## Context
We initiated the project with the goal of provisioning a multi-cloud infrastructure (Edge nodes, Lab cluster, Prod cluster) using Ansible from a WSL environment. The challenge lies in the diversity of cloud providers, where default system images vary significantly in their configuration (e.g., `sshd_config` defaults, root access policies).

## The Evolution of the Bootstrap Role

### 1. Initial State
The initial `bootstrap` role was a monolithic `main.yml` file that:
- Installed python dependencies.
- Created an admin user.
- Configured SSH keys.
- Ran `apt upgrade`.

**Problem:**
- `apt upgrade` processes often hang on interactive prompts (e.g., "Keep or replace config file?").
- Default cloud images have inconsistent `sshd_config` settings. Some allow password auth, others don't.
- Running `apt upgrade` *after* configuring SSH caused a race condition: if the package manager installed a new `sshd_config`, it could overwrite our custom security settings or fail due to conflict.

### 2. Architectural Decisions (ADR)

#### Decision 1: `force-confnew` Strategy
We decided to enforce a "Clean Slate" policy.
- **Why:** To ensure we are not building on top of legacy or vendor-specific configurations.
- **Implementation:** configured `apt` with `dpkg_options: 'force-confdef,force-confnew'`. This forces the system to install the package maintainer's latest version of configuration files, effectively resetting the system to a known standard before we apply our own configs.

#### Decision 2: Refactored Execution Order
We restructured the bootstrap flow to prevent configuration overwrites:
1.  **Init**: Install bare minimums (python, bash).
2.  **Update**: Run system upgrade and reset configs (`force-confnew`).
3.  **User**: Create the admin user.
4.  **SSH**: Apply *our* security configuration.
5.  **Reboot**.

**Benefit:** This ensures that our `sshd_config` is applied *after* the system update, guaranteeing our security policies are active.

#### Decision 3: Template-Based SSH Configuration
Instead of using `lineinfile` to patch `sshd_config` (which is fragile), we moved to a **Jinja2 Template** (`sshd_config.j2`).
- **Why:** To guarantee absolute consistency across all providers. We ignore the vendor's default file entirely and enforce our own standard.
- **Security Posture:**
    - `PermitRootLogin no`
    - `PasswordAuthentication no`
    - `PubkeyAuthentication yes`
    - `UsePAM yes`

#### Decision 4: Dynamic Swap Configuration
For Edge nodes (often low-memory VPS), we implemented a dynamic swap logic:
- If RAM < 1GB -> Create 1GB Swap.
- If RAM >= 1GB -> Create Swap equal to RAM size.
- This prevents OOM (Out Of Memory) issues on small instances.

## Outcome
The codebase now features a robust, modular `bootstrap` role that normalizes the environment across any Debian-based cloud instance, providing a consistent and secure foundation for the `site.yml` provisioning.
