Added support for `IPHost` attributes declaring `allow_prefix: false`. Their values are exposed as bare
`ipaddress.IPv4Address`/`IPv6Address` objects (no prefix), serialized back as a bare-address string, and
typed as `IPAddress` in generated protocols. `IPHost` attributes that do not declare the parameter keep
returning `ipaddress.IPv4Interface`/`IPv6Interface`, as does any attribute read from a server that does
not publish the parameter.

This replaces the `IPAddress` attribute kind announced earlier in this release cycle: no such attribute
kind exists on the Infrahub server, so the code paths handling it were unreachable and have been removed.
