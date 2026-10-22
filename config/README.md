# Rolling High Club — Configuration Templates

This directory contains **blank reusable mechanics schemas**. They are not active campaign facts merely because they exist.

- `ECONOMY_TEMPLATE.json` — generic business/economy mechanic configuration. Its `business_units` map holds inert Business Cards; each Card declares its same-day internal raw-material source links and a rolled Card also declares its `facility_value` repair-cost basis; `scripts/business_plan.py` validates them for POST-EV2-12.1 without resolving anything.
- `ORGANIZATION_TEMPLATE.json` — generic static organization/workforce configuration.

To use a template, create a separately named configuration file, populate only DM-approved values/rules, and explicitly establish that mechanic for RHC.

Static configuration describes rules and durable structure. Current money, damage, deployments, active effects and other mutable values belong in current-state domains.

Mission 10's Robbert Inc. names, money, workforce, facilities and economic values are intentionally **not copied** into these templates.
