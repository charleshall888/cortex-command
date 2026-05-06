# Sentinel fixture: deliberately broken citation

R10's parametrized negative-case variant runs the resolver over THIS file
and asserts the test detects the citation below as unresolvable.

The slug `this-slug-does-not-exist` has no directory at either
`lifecycle/this-slug-does-not-exist/` or
`lifecycle/archive/this-slug-does-not-exist/`.

See lifecycle/this-slug-does-not-exist/research.md for the broken target.
