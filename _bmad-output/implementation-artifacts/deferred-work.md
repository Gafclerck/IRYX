
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-analyseur-de-journaux-d-evenements-windows-evtx-python-evtx.md`
  summary: Ajouter une fixture EVTX binaire réelle (Security.evtx avec enregistrements 4624/4625) pour tester le parsing de bout en bout sans mock de python-evtx.
  evidence: Tous les tests d'extraction d'enregistrements mockent Evtx.Evtx ; seul le fichier vide exerce la vraie bibliothèque, donc les écarts entre mock et vrais objets Record ne seraient pas détectés.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-5-analyseur-d-artefacts-d-execution-windows-prefetch-dissect.md`
  summary: Ajouter une fixture Prefetch binaire compressée MAM réelle pour tester la décompression de bout en bout sans mock de dissect.util.lzxpress_huffman.
  evidence: Les tests unitaires actuels mockent lzxpress_huffman.decompress pour simuler des données SCCA valides; intégrer un fichier .pf Windows 10 réel exercera le décodage LZ-Xpress natif en conditions réelles.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-4-endpoints-de-consultation-et-telechargement-des-rapports-scelles.md`
  summary: Revenir sur le changement `fastapi` → `fastapi[standard]` et le churn de `uv.lock` une fois la story 8.4 terminée, si ces dépendances ne sont plus nécessaires.
  evidence: Modifications présentes dans l’arbre avant l’implémentation de la story et explicitement conservées à la demande de l’utilisateur ; elles ne sont pas causées par cette story et ne doivent pas être annulées ici.
