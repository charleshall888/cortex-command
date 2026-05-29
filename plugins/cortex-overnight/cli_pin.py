"""Side-effect-free declaration of the CLI version pin for cortex-overnight.

Element 0 is the git tag this plugin pins for CLI auto-install; element 1 is
the print-root JSON envelope schema major it requires. Kept in a sibling
module so both ``server.py`` and the SessionStart-async sync hook can import
the pin without pulling in the MCP server's runtime dependencies.
"""

CLI_PIN = ("v2.16.0", "2.0")
