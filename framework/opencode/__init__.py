"""The relocated framework surface: agents/, skills/, commands/, hooks/, rules/, scripts/,
plugin/, tools/ and the two registries (skill-routing.md, skill-integration-matrix.md).

A package marker, deliberately not an API: the contents are data (Markdown, TypeScript, bash)
shipped with the distribution and resolved at runtime via ``framework.locate.surface_root()``.
Declaring ``framework.opencode`` a package is what makes ``pip`` place the tree inside the wheel
so ``framework init`` can materialise it into an application repository.
"""
