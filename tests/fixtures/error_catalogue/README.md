# Error catalogue fixtures

Two envelope shapes appear here:

- **GraphQL** (`/graphql`), the catalogue envelope. Data failures arrive as HTTP 200 with an `errors`
  array; authentication failures arrive as a real 401 or 403. `extensions.code` is a catalogue code
  string.
- **REST** (`/api/...`), the legacy envelope, where `extensions.code` is an *integer* mirroring the
  HTTP status. It carries no catalogue code and no `data`.

The `graphql_*`, `auth_*`, and `rest_*` files are captured responses, kept in the shape the server
sends rather than hand-shaped to suit the parser. A fixture authored against the parser can only
prove the parser agrees with itself.

The `malformed_*` files are the exception: they are constructed, because a correct server does not
produce them. They stand in for a proxy, a gateway, or a future server that answers in a shape the
SDK does not expect, and they exist to pin that such a shape degrades rather than raising.

`public_names.json` is not an envelope. It is the committed snapshot of every exception class
importable from `infrahub_sdk.exceptions`, which pins that restructuring the module into a package
stays invisible from outside. It lists exception classes only; incidental typing imports that the
flat module used to re-export are not part of that surface and are no longer importable.
