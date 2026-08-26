Parts of the SDK no longer fail to import on a plain `pip install infrahub-sdk`.

`infrahub_sdk.template`, `infrahub_sdk.yaml`, `infrahub_sdk.spec`, `infrahub_sdk.transfer` and `infrahub_sdk.protocols_generator` import Jinja2, PyYAML and rich, but those three were only installed by the `ctl` extra. Using any of them without that extra raised `ModuleNotFoundError`, even though none of it is CLI-specific: `template` renders your Transforms, and rich supplies the traceback types carried in Jinja error reporting.

All three are now installed with the SDK itself, so a plain install grows from 19 to 26 packages. The `ctl` extra is correspondingly smaller and now covers only what `infrahubctl` genuinely needs.
