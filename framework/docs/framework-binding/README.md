# Framework binding — `framework.config.json`

## Why this exists

`framework.config.json` is **the one config the framework reads from the app repo**
(`framework/config_schema.json`, plan D3/D5–D8). Without it, `python framework/validate.py`
fails its own app suite:

```
FAIL  framework.config.json present — run `framework init` to bind this repository
FAIL  framework.config.json declares app_root — required by framework/config_schema.json
FAIL  framework.config.json declares state_folder — required by framework/config_schema.json
```

The file is a **plane path** (`AGENTS.md`; `framework/security/enforcement_plane.yaml`;
enforced by the `framework.config.json` edit deny in `opencode.json`), so an agent may not
write it. It is staged here as an exact new-file patch for a human to apply.

## What to apply

```bash
git apply --check framework/docs/framework-binding/framework-config.patch
git apply         framework/docs/framework-binding/framework-config.patch
python3 framework/validate.py; echo "exit=$?"     # expect 0
```

Roll back with `git apply -R framework/docs/framework-binding/framework-config.patch` (or just delete the
file — it is new).

## Why these values

```json
{
  "framework": { "distribution": "agentic-lifecycle" },
  "app_root": ".",
  "state_folder": ".planning"
}
```

- **`app_root: "."`** — the directory containing this config, i.e. the repository root. This is
  the schema's documented meaning of `"."`.
- **`state_folder: ".planning"`** — this repository's live GSD state lives in `.planning/` (the
  state adapter recognises `.planning` as `gsd-core`; it does not recognise `.framework/state`).
  `framework init`'s template defaults to `.framework/state` because it scaffolds a **new** app
  repo; pointing this repo there would desynchronise the adapter from the real state tree. With
  `"app_root": "."` and `"state_folder": ".planning"`, `framework/locate.py` resolves exactly
  the legacy locations, so the binding is behaviour-preserving.
- **`framework.distribution`** — pins the distribution name. `version`/`source` are omitted
  because this repository runs the framework in-tree rather than from an installed wheel; add
  them (via `framework init --source <ref>`) if you later pin a release.

One operational note: once a config exists, `framework/locate.py:manifest_dir()` moves the
detection caches from `framework/.manifest` to `<state_root>.parent/.manifest` (the repo
root's `.manifest/`). The caches are regenerated on demand; the old directory is inert.

## How this was verified without writing the plane file

The values were proven with the `FRAMEWORK_CONFIG` environment override (which
`framework/locate.py:find_config()` consults first), pointing at a config whose `app_root` was
the repository root — equivalent to `"."` when the config sits at that root:

```
VALIDATION PASSED  [profile=app; 0 fail, 0 warn, 0 not-applicable]
app_root   : <repo root>
state_root : <repo root>/.planning
```

Nothing in the repository was modified to run that check.
