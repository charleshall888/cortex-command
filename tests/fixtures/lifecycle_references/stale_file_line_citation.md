# Sentinel fixture: stale file_line_citation

Test #3's stale-citation regression variant runs the resolver over THIS
file and asserts the deliberately-stale `<file>:<line>` citation below
is detected (line beyond actual file line count).

The cited file `tests/fixtures/lifecycle_references/broken-citation.md`
exists in the repo and has fewer than 9999 lines. Pointing at line 9999
must trigger the line-count-exceeded detection path (see spec Req 9 and
ticket #181 Task 4 plan).

See tests/fixtures/lifecycle_references/broken-citation.md:9999 for the
deliberately-stale target citation.
