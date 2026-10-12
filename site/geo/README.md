# Vendored county map

`counties-10m.json` is copied unchanged from
[`@severo_bo/us-atlas-2023@4.0.0`](https://github.com/severo/us-atlas-2023):
the 2023 Census cartographic boundary files as TopoJSON, with the same layout as
`us-atlas`. See DECISIONS 008 for why it's used instead of `us-atlas@3.0.1`.

- Source: `https://cdn.jsdelivr.net/npm/@severo_bo/us-atlas-2023@4.0.0/counties-10m.json`
- SHA-256: `7d9efcb8fe58856d9fd955f7512e14901cfb9bffd4bd1353927d71169e24b4a7`
- License: ISC (see `LICENSE`)

The file also contains Puerto Rico and the other territories. The pipeline and
the page both filter them out at load time (DECISIONS 006). The file itself stays
untouched, so it can be checked against the checksum above.
