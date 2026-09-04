# Escape matrix and containment metrics

Spec: §12.5. Maintained **across** features, not per feature.

## Matrix

Rows are introduction phases, columns detection phases. Each defect is one cell.

|  | unit | integration | system | validation | production |
|---|---|---|---|---|---|
| requirements | | | | | |
| architecture | | | | | |
| contract | | | | | |
| detailed design | | | | | |
| implementation | | | | | |

## Derived indicators

| Indicator | Formula | Current |
|---|---|---|
| requirement escape rate | requirement-introduced defects detected at system or later / all requirement-introduced | |
| architecture escape rate | same shape | |
| contract escape rate | same shape | |
| design escape rate | same shape | |
| implementation escape rate | same shape | |
| phase containment effectiveness | caught in phase / (caught in phase + escaping phase) | |

## Preventive control improvement rate (§12.2) — v1.1

```
rate = escape corrections / process-originated defects
```

**Must equal 1.0.** This replaces the v1.0 metric of "every defect changed a checklist", which produced checklist inflation. A non-process-originated defect with no checklist change does not lower this rate — it is not in the denominator.

| Period | Defects | Process-originated | With escape correction | Rate |
|---|---|---|---|---|
| | | | | |

## Quarterly action

The two lowest-containment phases each get at least one concrete change to a checklist, template or gate. Record it here so the change is auditable.

| Quarter | Lowest-containment phases | Change made | Where |
|---|---|---|---|
