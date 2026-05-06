# Sentinel fixture: path-traversal in file_line_citation

Test #3's path-traversal regression variant runs the resolver over THIS
file and asserts the deliberately-traversal-attempting `<file>:<line>`
citation below is detected by the traversal-safety check (see spec Req 9
and ticket #181 Task 4 plan).

The citation below contains `..` segments and resolves outside the repo
root. The traversal-safety check rejects raw paths containing `..` AND
any resolved path that escapes REPO_ROOT.

Cited target: ../../etc/passwd.sh:1
Companion form (per spec Req 9 acceptance text): ../../etc/passwd:1
