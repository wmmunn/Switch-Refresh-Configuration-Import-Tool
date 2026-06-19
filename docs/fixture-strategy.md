# Fixture Strategy

This project uses sanitized fixtures to test parser and template behavior
without publishing private operational data.

## Fixture Safety Pipeline

Use this pipeline for any fixture derived from real operational configs:

```text
private source config
-> user-sanitized local intake
-> derived sanitized fixture candidate
-> local safety scan and review
-> public fixture only after explicit approval
```

Do not place semi-cleaned or review-pending configs directly in the public
repository.

## Sanitization Requirements

Public fixtures must avoid:

- Real hostnames, site codes, device names, usernames, and contact strings.
- Real domain names, email addresses, URLs, banners, or location text.
- Real management, server, gateway, or infrastructure IP addresses.
- RFC1918 private addressing unless there is a specific reason to test private
  address recognition. Prefer RFC documentation ranges.
- SNMP communities, RADIUS/TACACS keys, enable secrets, local user hashes, or
  certificate material.
- Interface descriptions that reveal real topology naming or operational
  conventions.
- Customer, employer, vendor account, circuit, asset, or contract references.

Preferred public addressing ranges:

- `192.0.2.0/24`
- `198.51.100.0/24`
- `203.0.113.0/24`

Preferred generic names:

- `DEMO-SW01`
- `DEMO_SITE`
- `DEMO_USERS`
- `DEMO_VOICE`
- `DEMO_MANAGEMENT`
- `DEMO_UPLINK_TO_DIST`
- `DEMO_PORT_CHANNEL`
- `DEMO-RADIUS-1`

## Fixture Shape

Fixtures should preserve realistic structure while removing real identity:

- Interface ordering.
- Interface block structure.
- VLAN and SVI patterns.
- Access-port, voice VLAN, trunk, uplink, and shutdown variations.
- Port-channel interfaces and member relationships.
- RADIUS/dot1x presence when the fixture is explicitly testing auth detection.
- Missing or partial sections when testing parser resilience.

The goal is real shape, fictional identity.

## Candidate Fixture Categories

Useful public fixture categories include:

- Basic Cisco IOS access switch without dot1x or port-channel.
- Cisco IOS access switch with dot1x/RADIUS detection.
- Cisco IOS access switch with synthetic port-channel uplinks.
- Generic refresh build template for placeholder injection.
- Small focused snippets for individual parser behaviors.

Avoid one large fixture that tries to cover every possible network feature.
Focused fixtures make parser behavior easier to review and safer to publish.

## Extraction Boundary

Fixtures should support targeted extraction, not full-config harvesting.

The import engine should extract only explicitly supported values needed by the
refresh build template. Unsupported sections may be ignored or flagged for
operator review, but should not be silently preserved in generated output.

## Current Local Groundwork

A local-only derived fixture set has been prepared outside the public
repository. It includes:

- A basic Cisco IOS access-switch fixture without dot1x or port-channel.
- An enhanced Cisco IOS access-switch fixture with synthetic RADIUS/dot1x and
  port-channel coverage.
- A generic refresh build template fixture with placeholders for future engine
  tests.

These files are not published in the repository yet. They should remain
local-only until reviewed again and intentionally promoted.

