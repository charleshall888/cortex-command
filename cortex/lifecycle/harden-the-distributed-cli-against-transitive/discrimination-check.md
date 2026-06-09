# Discrimination check — Task 6 (Spec Requirement 4 acceptance (b))

**Result: PASS.** The Task 4 route smoke test (`test_routes_smoke.py`) exits **non-zero (exit code 1)**
when run against the *pre-rewrite* name-first `app.py` on a fresh Starlette **1.2.1** resolve, failing with
`TypeError: ... unhashable type: 'dict'` in Jinja's template-cache key path. This proves the test genuinely
catches the regression rather than passing trivially on the dev venv's Starlette 0.52.1 (where both call
forms return 200).

## Why this one-time check is needed

On the dev venv (Starlette 0.52.1) the route test passes for BOTH the name-first
`TemplateResponse("name.html", {...})` form and the request-first `TemplateResponse(request, "name.html", {...})`
form, so locally it proves only well-formedness. The break only manifests on Starlette ≥1.0, where the removed
positional name-first signature binds the context dict into the `name` slot; that dict reaches Jinja's hashable
template-cache key and raises `TypeError: unhashable type: 'dict'` → HTTP 500. This check is the recorded proof
that the test discriminates at ≥1.0.

## Isolation method (live working tree never touched)

The check ran entirely in a throwaway `git worktree` + throwaway venv under `$TMPDIR`. No `git stash`, no
in-place revert; the live working tree's `app.py` and all tracked files were left untouched. The only tracked
file this task creates is this notes file.

## Refs and environment

- **Pre-rewrite (name-first) commit ref**: `4af68ab4` — the parent of the Task 1 commit `666f54d6`
  ("Rewrite dashboard TemplateResponse calls to request-first form"). `app.py` at `4af68ab4` is byte-identical
  to the pre-feature baseline `645bab65` (`git diff 645bab65 4af68ab4 -- cortex_command/dashboard/app.py` is
  empty), so either ref yields the same name-first code. The name-first form was confirmed at the call sites,
  e.g. `templates.TemplateResponse("base.html", {"request": request, ...})`.
- **Test source**: `cortex_command/dashboard/tests/test_routes_smoke.py` from the current branch (added by
  Task 4, commit `a7a3b701`). It does not exist at `4af68ab4`, so the OLD name-first `app.py` was combined
  with the CURRENT test.
- **Resolved Starlette version**: **1.2.1** (fresh, constraints-free resolve under the new pyproject bounds
  `starlette>=0.49.1,<2.0`; `pip show starlette` → `Version: 1.2.1`). Companion resolve: fastapi 0.136.3,
  jinja2 3.1.6, httpx 0.28.1, Python 3.14.5.
- **Pytest exit code**: **1** (non-zero). Summary: `13 failed, 2 passed, 1 warning`. The 2 passes are the
  non-render guards (`test_all_ten_partial_routes_covered`, the partial-route inventory check, and the
  `PARTIAL_ROUTES` cardinality assertion); all 13 render-path cases failed.

## Exact commands

```
# 1. Throwaway worktree at the pre-rewrite (name-first) commit
git worktree add --detach "$TMPDIR/discrim" 4af68ab4

# 2. Bring in the CURRENT Task 4 test (absent at 4af68ab4)
cp cortex_command/dashboard/tests/test_routes_smoke.py \
   "$TMPDIR/discrim/cortex_command/dashboard/tests/test_routes_smoke.py"

# 3. Fresh, constraints-free venv + install of the throwaway package -> resolves Starlette >=1.0
python3 -m venv "$TMPDIR/discrim-venv"
"$TMPDIR/discrim-venv/bin/pip" install "$TMPDIR/discrim" httpx pytest
"$TMPDIR/discrim-venv/bin/pip" show starlette        # -> Version: 1.2.1

# 4. Run the Task 4 test against the name-first app from a NEUTRAL cwd so the import
#    resolves to the installed (name-first) site-packages copy, not the live tree.
#    The test file is copied alongside the installed package for the same reason.
SITE=.../discrim-venv/lib/python3.14/site-packages
cp "$TMPDIR/discrim/cortex_command/dashboard/tests/test_routes_smoke.py" \
   "$SITE/cortex_command/dashboard/tests/test_routes_smoke.py"
cd "$TMPDIR" && "$TMPDIR/discrim-venv/bin/pytest" \
   "$SITE/cortex_command/dashboard/tests/test_routes_smoke.py" -q
# -> exit code 1; 13 failed, 2 passed

# 5. Teardown
git worktree remove --force "$TMPDIR/discrim"
rm -rf "$TMPDIR/discrim-venv"
```

### Import-resolution note (why the neutral cwd / site-packages copy)

`sys.path[0]` is `''` (the cwd). Running pytest with the live repo as cwd would shadow the installed name-first
`cortex_command` with the live tree's *request-first* `app.py`, silently defeating the check. The run was
therefore executed from a neutral cwd (`$TMPDIR`) against the installed package's name-first copy, and the test
file was copied into that installed package's `tests/` dir. Verified before running:
`python -c "import cortex_command.dashboard.app as m; print(m.__file__)"` from the neutral cwd resolved to
`.../discrim-venv/lib/python3.14/site-packages/cortex_command/dashboard/app.py`, and that copy is name-first.

## Quoted failing traceback excerpt (captured, not paraphrased)

The first failing case, `test_route_renders_200[/]`, with the cache-key value showing the context dict bound
into the `name` slot reaching Jinja's `LRUCache`:

```
discrim-venv/lib/python3.14/site-packages/cortex_command/dashboard/app.py:289: in session_detail
    return templates.TemplateResponse(
discrim-venv/lib/python3.14/site-packages/starlette/templating.py:148: in TemplateResponse
    template = self.get_template(name)
discrim-venv/lib/python3.14/site-packages/starlette/templating.py:115: in get_template
    return self.env.get_template(name)
discrim-venv/lib/python3.14/site-packages/jinja2/environment.py:1016: in get_template
    return self._load_template(name, globals)
discrim-venv/lib/python3.14/site-packages/jinja2/environment.py:964: in _load_template
    template = self.cache.get(cache_key)
discrim-venv/lib/python3.14/site-packages/jinja2/utils.py:477: in get
    return self[key]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <LRUCache {}>
key = (<weakref at 0x10c90af20; to 'jinja2.loaders.FileSystemLoader' at 0x10c643e00>, {'detail': None, 'request': <starlette.requests.Request object at 0x10cf45bd0>})

    def __getitem__(self, key: t.Any) -> t.Any:
        ...
        with self._wlock:
>           rv = self._mapping[key]
E           TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')

discrim-venv/lib/python3.14/site-packages/jinja2/utils.py:515: TypeError
```

The same `TypeError: ... unhashable type: 'dict'` recurred for all 13 render-path routes. The `cache_key` is a
2-tuple `(loader_weakref, <context dict>)`: because the context dict was passed positionally into the `name`
slot, it propagated to the cache key, which Jinja then tries to hash — hence "cannot use 'tuple' as a dict key
(unhashable type: 'dict')".

## Minor deviation from the spec's literal expectation (non-material)

The spec phrases the expected failure as `TypeError: unhashable type: 'dict'` → HTTP 500 failing the test's 200
assertions. Under Starlette 1.2.1, `starlette.testclient.TestClient` defaults to `raise_server_exceptions=True`,
so the server-side `TypeError` is **re-raised at `client.get(route)`** rather than being converted to a 500
response that the `assert status_code == 200` line then catches. The root cause, error type, and message are
exactly as specified (`TypeError: ... unhashable type: 'dict'` from the name-first form); only the surface — a
raised exception vs. a returned 500 — differs. Either way the test exits non-zero, which is the discrimination
signal the acceptance criterion requires. The starlette message string is also slightly richer on 1.2.1
(`cannot use 'tuple' as a dict key (unhashable type: 'dict')`) but contains the required `unhashable type: 'dict'`
substring verbatim.

## Teardown

The throwaway worktree (`git worktree remove --force`) and venv (`rm -rf`) were removed after capture. The live
working tree was never modified (no `app.py` edit, no stash, no revert), so this check could not race or corrupt
sibling tasks.
