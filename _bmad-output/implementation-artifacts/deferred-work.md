
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-analyseur-de-journaux-d-evenements-windows-evtx-python-evtx.md`
  summary: Ajouter une fixture EVTX binaire réelle (Security.evtx avec enregistrements 4624/4625) pour tester le parsing de bout en bout sans mock de python-evtx.
  evidence: Tous les tests d'extraction d'enregistrements mockent Evtx.Evtx ; seul le fichier vide exerce la vraie bibliothèque, donc les écarts entre mock et vrais objets Record ne seraient pas détectés.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-5-analyseur-d-artefacts-d-execution-windows-prefetch-dissect.md`
  summary: Ajouter une fixture Prefetch binaire compressée MAM réelle pour tester la décompression de bout en bout sans mock de dissect.util.lzxpress_huffman.
  evidence: Les tests unitaires actuels mockent lzxpress_huffman.decompress pour simuler des données SCCA valides; intégrer un fichier .pf Windows 10 réel exercera le décodage LZ-Xpress natif en conditions réelles.
