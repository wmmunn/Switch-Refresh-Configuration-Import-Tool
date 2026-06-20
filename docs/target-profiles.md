# ⚙️ Target Profile Configuration Guide (`.json`)

The **Target Build Planner** uses a JSON configuration profile to translate your old switch ports to your new switch hardware. Instead of making blind guesses, the engine relies on this file to safely map your stack members, bulk access ports, and static uplinks.

This document explains how to write, modify, and troubleshoot these files.

---

## 🚀 Quick-Start Example

Save this layout as a `.json` file (e.g., `c9300_refresh.json`) to use as your starting baseline. This template maps a legacy 3-switch stack to a clean, matching 3-switch high-speed stack.

```json
{
  "profile_name": "Standard-C9300-Refresh",
  "description": "Maps a legacy 3-switch 1G access stack to a new 3-switch 10G access stack",

  "stack_member_mappings": {
    "1": 1,
    "2": 2,
    "3": 3
  },

  "interface_renaming_rules": {
    "source_prefix": "GigabitEthernet",
    "target_prefix": "TenGigabitEthernet",
    "range_start": 1,
    "range_end": 48
  },

  "uplink_destinations": {
    "GigabitEthernet1/0/49": "TenGigabitEthernet1/1/1",
    "GigabitEthernet1/0/50": "TenGigabitEthernet1/1/2",
    "GigabitEthernet2/0/49": "TenGigabitEthernet2/1/1",
    "Port-channel1": "Port-channel10"
  }
}
```

---

## 🔧 Field Reference: What to Edit

### 1. `stack_member_mappings`

Maps old physical stack member IDs to your new physical member IDs.

- **Format**: `"OldMemberID": NewMemberID`
- **1:1 Migration (Standard)**: `"2": 2` keeps old Switch 2 ports mapped directly onto new Switch 2.
- **Stack Expansion**: If you are adding an extra switch into a stack to free up dense capacity, you can cleanly shift port lines over (e.g., `"3": 3`).

> ⚠️ **Design Note on Port Capacity**: Never map two highly populated 48-port legacy switches to the same target switch number (such as `"2": 2` and `"3": 2`). Doing so will cause the tool's mapping engine to throw immediate **Critical Collision** alerts in the GUI audit panel, as multiple old interfaces fight for the exact same target port space (e.g., trying to put both old port `2/0/5` and old port `3/0/5` onto the new target port `2/0/5`).

### 2. `interface_renaming_rules`

Automates bulk access-port renaming so you don't have to map all 48 ports manually.

- `source_prefix`: Matches your legacy configuration naming convention (e.g., `FastEthernet` or `GigabitEthernet`).
- `target_prefix`: The media speed string for your new hardware (e.g., `TenGigabitEthernet` for 10G, `TwentyFiveGigE` for 25G).
- `range_start` & `range_end`: Defines the boundary for bulk renaming (typically `1` and `48`). This restricts the bulk engine to standard user drops and safely protects your dedicated uplink ports from accidental name corruption.

### 3. `uplink_destinations`

Provides absolute overrides for infrastructure, distribution, and core links.

- **Format**: `"OldInterfaceName": "NewInterfaceName"`
- **Physical Ports**: Maps a specific physical port (e.g., `"GigabitEthernet1/0/49": "TenGigabitEthernet1/1/1"`).
- **Logical Bundles**: Maps entire port-channel groupings directly (e.g., `"Port-channel1": "Port-channel10"`).

---

## ⚠️ The "Expose, Don't Guess" Rule

The mapping engine is built with safety overrides to ensure bad configurations are caught before they touch your live network. If your JSON profile introduces logical errors, or if the source configuration contains ambiguous or unsupported patterns, the GUI's **Audit Panel** will throw explicit warnings rather than silently guessing. Categories you may see include:

- **Critical Collisions**: If your layout accidentally points two different legacy source ports to the exact same new destination port, the tool flags both lines together with shared collision evidence.
- **Unmapped Warnings**: If a port falls outside your defined `range_end` boundary (like port 49) and is missing from your explicit `uplink_destinations` block, it will be left completely unconfigured for manual operator validation.
- **Unsupported Interface Names**: Source interfaces that don't match a recognized naming pattern (e.g., legacy `Ethernet` ports) are left unmapped and flagged rather than guessed at.
- **Non-Identity Stack Member Shifts**: Any stack member mapping other than 1:1 (e.g., `"1": 2`) is flagged for review, even when it's collision-free, since it changes physical port identity.
- **Trunk Evidence, Not Resolution**: Trunk allowed-VLAN data (including multi-line `add`/`remove`/`except` statements) is preserved and surfaced for review. The engine does not yet compute the final effective VLAN set — it stages the evidence so you can verify it yourself.
- **Malformed Parser Blocks**: Source config blocks the parser can't confidently interpret are flagged rather than skipped or guessed.

A clean audit panel does not mean the output is approved for device deployment. For the full design rationale behind these review categories, see [`STRUCTURAL_CODE_AUDIT_NOTES.md`](https://github.com/wmmunn/Switch-Refresh-Configuration-Import-Tool/blob/master/STRUCTURAL_CODE_AUDIT_NOTES.md) and [`docs/profile-engine-design-notes.md`](https://github.com/wmmunn/Switch-Refresh-Configuration-Import-Tool/blob/master/docs/profile-engine-design-notes.md).
