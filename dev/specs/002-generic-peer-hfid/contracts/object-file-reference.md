# Contract: peer references in object files

This is the user-facing format for files with `apiVersion: infrahub.app/v1` and `kind: Object`.

## Relationship of cardinality one

```yaml
# Existing forms (unchanged)
parent_interface: [router1, Gi0/0/3]      # HFID list
parent_interface: Gi0/0/3                  # one-part HFID or ID

# New form
parent_interface:
  kind: InterfacesPhysicalInterface        # node kind that is the peer kind or inherits from it
  hfid: [router1, Gi0/0/3]                 # string or list of strings
```

## Relationship of cardinality many

```yaml
member_interfaces:
  - [router1, Gi0/0/1]                     # resolved by HFID alone when the peer generic has no HFID
  - kind: InterfacesPhysicalInterface
    hfid: [router1, Gi0/0/2]
```

## Error messages

Each message starts with the object's position in the file, for example `3.parent_interface: ...`. The text is the contract. The exact wording can change, but each message must contain the values in angle brackets.

| Case | When reported | Message contains |
|------|---------------|------------------|
| Kind does not inherit from the peer | validate and load | `<kind>` is not `<peer kind>` and does not inherit from it |
| Kind has no HFID | validate and load | `<kind>` has no human_friendly_id |
| Wrong number of HFID parts | validate and load | expected `<n>` values for `<kind>` (`<hfid paths>`), got `<m>` |
| Unknown key in the reference mapping | validate and load | only `kind` and `hfid` are allowed |
| No node matches (HFID alone, generic peer) | load | no `<peer generic>` with HFID `<hfid>` among `<candidate kinds>` |
| More than one node matches | load | HFID `<hfid>` matches `<kind A>`, `<kind B>`; add `kind:` to the reference |
