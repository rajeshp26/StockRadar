# Bash hygiene

Bash is for git state, test/build/lint runners, and trusted framework scripts - not for
inspection, not for file management, not for one-off scripts. The permission allowlist is
stable; command construction must fit it, not grow it.

## Core principle

Do not use Bash as a general-purpose scripting environment when a file/tool can perform the
same operation. Every command that falls outside the allow families is a prompt; every prompt
an agent learns to avoid by rephrasing is a policy evasion.

## Rules

1. **Prefer native tools for inspection.** Read/Grep/Glob for files, LSP/codegraph for
   structure, context7 for docs, the browser MCP for pages. Get-Content/Select-String in
   PowerShell are last resorts, not defaults.

2. **One command per invocation.** Never chain with `;`, `&&`, or `|`. A chain hides the
   second command behind the first command's permission match and defeats the policy.

3. **Trusted scripts over inline code.** `python framework/.../script.py` over
   `python -c "..."` or heredocs. An inline block is code without a home; it gets rewritten,
   re-prompted, and re-matched.

4. **Never rephrase to dodge a prompt.** A denied operation is denied; an ask is a
   checkpoint. Restating `Remove-Item x` as `rm x`, or `git push` as `git push origin`, is a
   policy violation. If an operation is legitimate but blocked, request a rule change with
   justification - do not route around it.

5. **Do not add permission matchers reactively.** Before proposing an allow rule, name the
   recurring workflow that needs it, confirm no native tool or trusted script covers it, and
   state which safe family it belongs to. One prompt is not a recurring workflow; a path
   allow over a mixed-risk directory (e.g. `backend/scripts/`) is never justified.

6. **No bare file/directory creation from Bash.** Write/Edit tools create files; a trusted
   script creates its own directories. `New-Item` and bare `mkdir` from an agent are not
   allowlisted and should not be requested.

7. **Windows is PowerShell 5.1.** Use explicit verbs (`Remove-Item`, not `del`/`rm`).
   Prefer the allowlisted cmdlets (`Get-ChildItem`, `Get-Content`, `Test-Path`) over
   POSIX-style equivalents.

8. **Three arguments of inline logic means it belongs in a file.** A command that needs
   quoting, loops, or conditionals is a script: put it in `framework/tools/` with the
   permission it needs, or make it a test.

## The permission model this sustains

| Class | Policy |
|---|---|
| Read repo / git state | allow |
| Tests, build, lint, typecheck | allow |
| Trusted framework scripts and gates | allow |
| Arbitrary shell / python / installs | ask |
| Destructive fs, git history mutation, push | deny |

Hygiene keeps engineering operations in the top three rows. The config never grows to fit
bad command construction; command construction shrinks to fit the config.