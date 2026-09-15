# F1 — Feature Understanding

```
Charter: researcher
Agent-Id: <...>
Role: researcher
Session-Id: <...>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase: F1
Baseline: pre-baseline
Timestamp: <ISO 8601 with offset>
```

Spec: §5.1. Every claim is `[verified: source]`, `[inferred]`, or `[assumption: how to verify]`.

## 0. Grilling pass (v1.2 addendum — see `researcher.md`)

Answered before the tables below, not after. Skip only for a change with no ambiguity to surface — record that decision, don't just leave this section blank.

| Question asked | Why it mattered | Answer | Marker |
|---|---|---|---|
| | | | |

## 1. Customers

| Id | Customer | Why they touch this feature |
|---|---|---|
| CUS-1 | | |

Candidates: driver, front passenger, rear passenger, owner, non-owner user, guest, fleet operator, dealer, service technician, administrator, backend operator, another software system. Multiple customers get separate ids.

## 2. Environment — every dimension answered, none "unknown"

General baseline from `config.yml` `environment_baseline.general`:

| Dimension | Exposure | Source |
|---|---|---|
| vehicle_state | | |
| ignition_power_state | | |
| connectivity | | |
| network_availability | | |
| location_region | | |
| user_account_state | | |
| device_state | | |
| active_media_source | | |
| vehicle_configuration_variant | | |
| software_version | | |
| hardware_variant | | |
| language | | |
| privacy_settings | | |
| permissions | | |
| driving_context | | |
| online_offline | | |
| time | | |

Audio-specific from `environment_baseline.audio_specific`:

| Dimension | Exposure | Source |
|---|---|---|
| active_audio_focus_owner | | |
| ducking_state | | |
| mute_state | | |
| active_zones | | |
| concurrent_stream_count | | |
| output_endpoint_set | | |
| amplifier_or_dsp_variant | | |
| occupancy_per_seat | | |

## 3. Operating conditions

Classify each relevant condition: `normal`, `degraded`, `unavailable`, `failure`, `recovery`, `interrupted`, `concurrent`, `repeated`, `boundary`, `misuse`, `unexpected_sequence`.

| Condition | Class | What it looks like here |
|---|---|---|
| | | |

## 4. Constraints, dependencies, assumptions

| Item | Kind | Owner | Verification route |
|---|---|---|---|
| | constraint / dependency / assumption | | |

## 5. Prior art and existing behaviour — feeds F10 reverse impact

| Existing mechanism or behaviour | Where | Relevance |
|---|---|---|
| | | |

## 6. Exit criteria

- [ ] Grilling pass performed or explicitly waived with a reason (§0)
- [ ] No environment dimension left "unknown"
- [ ] Every assumption has a route to resolution
- [ ] Every claim carries its `[verified/inferred/assumption]` marker
- [ ] Existing-behaviour findings recorded for F10
